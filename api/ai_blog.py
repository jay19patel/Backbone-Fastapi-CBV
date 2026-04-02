from __future__ import annotations
import operator
import os
import urllib.parse
from typing import TypedDict, List, Optional, Literal, Annotated, Dict, Any, Tuple

from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from schemas.blogs import (
    BlogSection, BlogSectionText, BlogSectionBullets, BlogSectionTable,
    BlogSectionNote, BlogSectionLinks, BlogSectionImage, BlogSectionCode,
    BlogSectionYoutube, BlogSectionFlowchart, BlogSectionFlowchartStep,
    BlogPromptState
)
from backbone.core.settings import settings

# Instantiated lazily to prevent uvicorn boot crash if API key is missing
def get_llm():
    return ChatGoogleGenerativeAI(
        model=settings.PRODUCTION_LLM_MODEL,
        google_api_key=settings.GOOGLE_API_KEY,
        temperature=0.7
    )

# --- 1. Schemas ---

class BlogContentSchema(BaseModel):
    introduction: str
    sections: List[BlogSection]
    conclusion: str

class BlogPromptStateStructured(BaseModel):
    """A heavily structured version of BlogPromptState for OpenAI to output"""
    title: str
    subtitle: Optional[str] = None
    excerpt: Optional[str] = None
    image: Optional[str] = None
    category: Optional[str] = None
    tags: List[str] = []
    content: BlogContentSchema

class Task(BaseModel):
    id: int
    title: str
    goal: str = Field(..., description="One sentence describing what the reader should do/understand.")
    bullets: List[str] = Field(..., min_length=3, max_length=6)
    tags: List[str] = Field(default_factory=list)

class Plan(BaseModel):
    title: str
    subtitle: str
    excerpt: str
    category: str
    tags: List[str]
    introduction: str
    conclusion: str
    tasks: List[Task] = Field(..., description="List of 3 to 7 tasks/sections to generate")

class SectionOutput(BaseModel):
    sections: List[BlogSection]

class RouterDecision(BaseModel):
    mode: Literal["edit", "generate", "chat"]
    reason: str

class WorkflowState(TypedDict):
    prompt: str
    session_id: str
    previous_state: Optional[Dict[str, Any]]
    
    # Internal routing
    mode: Optional[str]
    chat_response: Optional[str]
    
    # Generation parts
    plan: Optional[Plan]
    task_sections: Annotated[list, operator.add]
    
    # Result
    final_blog_state: Optional[BlogPromptStateStructured]


# --- 2. Nodes ---

ROUTER_SYSTEM = """You are an advanced blog orchestrator router.
Analyze the user's prompt to determine if they are asking to EDIT an existing blog, GENERATE a completely new blog, or just casually CHATTING.
- If they reference the existing blog or ask for modifications (e.g., "update the title", "make it funnier"), output 'edit'.
- If they ask for a brand new topic or say something like "write a blog about React", output 'generate'.
- If they send a casual greeting (e.g., "Hi", "Hello") or ask a general chatty question not related to blogging, output 'chat'.
"""

def router_node(state: WorkflowState) -> dict:
    decider = get_llm().with_structured_output(RouterDecision)
    decision = decider.invoke([
        SystemMessage(content=ROUTER_SYSTEM),
        HumanMessage(content=f"User prompt: {state['prompt']}\nPrevious state exists: {'Yes' if state.get('previous_state') else 'No'}")
    ])
    return {"mode": decision.mode}


def route_next(state: WorkflowState) -> str:
    path = state.get("mode") or "generate"
    if path == "chat":
        return "chatter"
    return "editor" if path == "edit" else "orchestrator"

CHATTER_SYSTEM = """You are a friendly, helpful AI Blog Generator assistant. 
The user is just chatting with you naturally without asking you to create or edit a blog right now.
Respond politely and conversationally, perhaps asking what they'd like to write their blog about today.
Keep it concise.
"""

def chatter_node(state: WorkflowState) -> dict:
    chat_llm = get_llm()
    result = chat_llm.invoke([
        SystemMessage(content=CHATTER_SYSTEM),
        HumanMessage(content=state['prompt'])
    ])
    return {"chat_response": result.content}


EDITOR_SYSTEM = """You are an expert technical editor.
Your job is to apply the user's instructions to strictly modify the provided JSON blog state.
Maintain the exact structure. Keep all unchanged parts identical.
If the user says "update the title", ONLY change the title and keep the remaining content essentially identical.

Output the complete, fully-valid JSON matching the structured schema.
"""

def editor_node(state: WorkflowState) -> dict:
    editor_llm = get_llm().with_structured_output(BlogPromptStateStructured)
    result = editor_llm.invoke([
        SystemMessage(content=EDITOR_SYSTEM),
        HumanMessage(content=f"User instructions: {state['prompt']}\n\nPrevious State:\n{state['previous_state']}")
    ])
    return {"final_blog_state": result}


ORCH_SYSTEM = """You are a senior developer advocate planning a technical blog post.
The JSON output should adhere strictly to the schema.
Provide a compelling title, subtitle, excerpt, category, tags, an introduction paragraph, a conclusion paragraph, and an outline of tasks (each task will be expanded into one or more rich sections).
"""

def orchestrator_node(state: WorkflowState) -> dict:
    planner = get_llm().with_structured_output(Plan)
    plan = planner.invoke([
        SystemMessage(content=ORCH_SYSTEM),
        HumanMessage(content=f"Topic / Prompt: {state['prompt']}")
    ])
    return {"plan": plan}


def fanout(state: WorkflowState):
    plan = state["plan"]
    if not plan:
        return []
    
    sends = []
    for task in plan.tasks:
        sends.append(
            Send("worker", {
                "task": task.model_dump(),
                "plan_context": {
                    "title": plan.title,
                    "category": plan.category,
                }
            })
        )
    return sends


WORKER_SYSTEM = """You are a technical writer generating ONE specific block/task of a blog post.
You must output a List of valid JSON objects corresponding to BlogSection types.
Use a diverse mix of rich media sections. You MUST prioritize 'text', 'table', and 'flowchart' sections.

Strict JSON Output Format Requirements:
Each section MUST be a JSON object containing a "type" key mapping to one of the allowed types.
Here are the exact expected schemas for the sections:

1. Text Section:
{
  "title": "Optional Heading (can be omitted)",
  "type": "text",
  "content": "Detailed paragraphs of markdown text explaining the topic clearly."
}

2. Bullets Section:
{
  "title": "Optional Heading",
  "type": "bullets",
  "items": ["First key point", "Second key point", "Third key point"]
}

3. Code Section:
{
  "title": "Optional Heading",
  "type": "code",
  "language": "python",
  "content": "def example():\n    pass"
}

4. Note/Callout Section:
{
  "title": "Optional Heading",
  "type": "note",
  "content": "Important warning, tip, or callout text goes here."
}

5. Table Section:
{
  "title": "Comparison of Systems",
  "type": "table",
  "headers": ["Feature", "Option A", "Option B"],
  "rows": [
      ["Speed", "Fast", "Slow"],
      ["Cost", "Free", "Paid"]
  ]
}

6. Flowchart Section:
{
  "title": "Architecture Flow",
  "type": "flowchart",
  "steps": [
    {
      "id": "step1",
      "title": "Start Process",
      "description": "Initialization phase description",
      "color": "blue",
      "branches": []
    }
  ]
}

CRITICAL INSTRUCTIONS: 
1. DO NOT ever use or output the 'image' type. It is strictly forbidden.
2. You MUST strictly use the exact JSON structures listed above. Do not hallucinate random properties.
3. You MUST explicitly include the "type" key string in every section object.
4. Completely fill out the content. Never output empty strings, empty arrays, or blank sections.

For example, if explaining a comparison, output an object with type='text' followed by an object with type='table'. 
Be creative, accurate, and ensure high-quality technical formatting and explicit code snippets.
"""

def worker_node(payload: dict) -> dict:
    task = Task(**payload["task"])
    
    worker_llm = get_llm().with_structured_output(SectionOutput)
    
    bullets = "\n- ".join(task.bullets)
    out = worker_llm.invoke([
        SystemMessage(content=WORKER_SYSTEM),
        HumanMessage(content=(
            f"Blog Title Context: {payload['plan_context']['title']}\n"
            f"Task Title: {task.title}\n"
            f"Goal: {task.goal}\n"
            f"Points to cover:\n- {bullets}\n\n"
            "Return the sections to satisfy this task."
        ))
    ])
    
    # Store as a tuple of (task_id, sections) to preserve order
    return {"task_sections": [(task.id, out.sections)]}


def reducer_node(state: WorkflowState) -> dict:
    plan = state["plan"]
    # Sort the task sections by Task ID
    ordered_sections = [sections for _, sections in sorted(state.get("task_sections", []), key=lambda x: x[0])]
    
    # Flatten list of lists
    flat_sections = []
    for s_list in ordered_sections:
        flat_sections.extend(s_list)
        
    import uuid
    # Using picsum.photos for a stable, high-quality placeholder image instead of fragile AI generation
    seed = urllib.parse.quote(plan.title.replace(" ", "")[:15] or str(uuid.uuid4())[:8])
    dynamic_cover = f"https://picsum.photos/seed/{seed}/1280/720"

    final_state = BlogPromptStateStructured(
        title=plan.title,
        subtitle=plan.subtitle,
        excerpt=plan.excerpt,
        category=plan.category,
        tags=plan.tags,
        image=dynamic_cover,
        content=BlogContentSchema(
            introduction=plan.introduction,
            sections=flat_sections,
            conclusion=plan.conclusion
        )
    )
    
    return {"final_blog_state": final_state}


# --- 3. Graph Construction ---

g = StateGraph(WorkflowState)

g.add_node("router", router_node)
g.add_node("editor", editor_node)
g.add_node("orchestrator", orchestrator_node)
g.add_node("worker", worker_node)
g.add_node("reducer", reducer_node)
g.add_node("chatter", chatter_node)

g.add_edge(START, "router")
g.add_conditional_edges("router", route_next, {"editor": "editor", "orchestrator": "orchestrator", "chatter": "chatter"})

g.add_edge("chatter", END)
g.add_edge("editor", END)

g.add_conditional_edges("orchestrator", fanout, ["worker"])
g.add_edge("worker", "reducer")
g.add_edge("reducer", END)

ai_blog_generator = g.compile()


def generate_or_edit_blog(prompt: str, session_id: str, previous_state: Optional[Dict[str, Any]] = None) -> Tuple[Optional[BlogPromptState], Optional[str]]:
    """Wrapper to run the graph and return the frontend-friendly dict."""
    result = ai_blog_generator.invoke({
        "prompt": prompt,
        "session_id": session_id,
        "previous_state": previous_state,
        "plan": None,
        "task_sections": []
    })
    
    if result.get("chat_response"):
        if previous_state:
            return BlogPromptState(**previous_state), result["chat_response"]
        return None, result["chat_response"]
        
    final: BlogPromptStateStructured = result["final_blog_state"]
    # Convert typed strongly-schema to the open BlogPromptState
    blog_state = BlogPromptState(
        title=final.title,
        subtitle=final.subtitle,
        excerpt=final.excerpt,
        image=final.image,
        category=final.category,
        tags=final.tags,
        content=final.content.model_dump()
    )
    return blog_state, None


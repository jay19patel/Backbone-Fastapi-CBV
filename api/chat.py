from fastapi import APIRouter, HTTPException, Depends, Request
from typing import List, Optional, Any, Dict, Union
from pydantic import BaseModel, Field
import uuid
from schemas.blogs import Blog, BlogSection, BlogSectionFlowchartStep

router = APIRouter()

# --- Schemas ---

class GenerateBlogRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

from schemas.blogs import Blog, BlogSection, BlogSectionFlowchartStep, BlogPromptState

class GenerateBlogResponse(BaseModel):
    action: str = "generate"
    session_id: str
    conversation: List[Dict[str, str]]
    blog_state: Optional[BlogPromptState] = None

# --- Mock Database / Session Store ---
_sessions = {}
_blog_states = {}

from api.ai_blog import generate_or_edit_blog

# --- Endpoints ---

@router.post("/generate/", response_model=GenerateBlogResponse)
async def generate_chat(request: GenerateBlogRequest):
    session_id = request.session_id or str(uuid.uuid4())
    
    if session_id not in _sessions:
        _sessions[session_id] = []
    
    # Add user message
    _sessions[session_id].append({"role": "user", "content": request.message})
    
    prev_state = _blog_states.get(session_id)
    
    try:
        # Generate or Edit using AI Graph
        import asyncio, functools
        loop = asyncio.get_event_loop()
        blog_state, chat_msg = await loop.run_in_executor(
            None,
            functools.partial(
                generate_or_edit_blog,
                prompt=request.message,
                session_id=session_id,
                previous_state=prev_state.model_dump() if prev_state else None
            )
        )
        
        # Save to session (if there's a new blog state)
        if blog_state:
            _blog_states[session_id] = blog_state
        
        if chat_msg:
            assistant_message = chat_msg
        else:
            assistant_message = f"I've updated the draft for your blog: **{blog_state.title}**. You can see the structure populated in the form below."
    except Exception as e:
        blog_state = prev_state
        assistant_message = f"I encountered an error generating the blog: {str(e)}"
    
    _sessions[session_id].append({"role": "assistant", "content": assistant_message})
    
    return {
        "session_id": session_id,
        "conversation": _sessions[session_id],
        "blog_state": blog_state
    }

@router.get("/session/{session_id}/")
async def get_session(session_id: str):
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"conversation": _sessions[session_id]}

@router.post("/save/")
async def save_chat_blog(request: Dict[str, str]):
    # In a real app, this would commit the session state to the Blog collection
    return {"message": "Blog generated and ready for final review!"}

@router.delete("/session/{session_id}/")
async def delete_session(session_id: str):
    if session_id in _sessions:
        del _sessions[session_id]
    if session_id in _blog_states:
        del _blog_states[session_id]
    return {"status": "success"}

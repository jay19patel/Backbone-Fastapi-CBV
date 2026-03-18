from typing import Any, Optional, Annotated, Type, Union
from pydantic import Field, PlainSerializer
from beanie import Link

# --- Base Fields ---

# The "Name" Type
Name = Annotated[str, Field(max_length=200)]

# The "Text" Type
Text = Annotated[Optional[str], Field(default=None)]

# The "Int" Type
Int = Annotated[int, Field(default=0)]

# The "Bool" Type
Bool = Annotated[bool, Field(default=True)]

def TextField(label: str, max_length: Optional[int] = None, **kwargs) -> Any:
    return Annotated[str, Field(description=f"Enter {label}", max_length=max_length, **kwargs)]

def IntField(label: str, default: int = 0, **kwargs) -> Any:
    return Annotated[int, Field(description=f"Enter {label}", default=default, **kwargs)]


# --- Media Fields ---

def serialize_attachment(value: Any) -> Any:
    if not value: return None
    from backbone.core.url_utils import get_media_url
    
    path = None
    # 1. Unpack Beanie Links
    if hasattr(value, "ref"):
        if hasattr(value, "doc") and getattr(value, "doc", None):
            value = value.doc
        else:
            return str(value.ref.id)

    # 2. Extract path
    if isinstance(value, dict):
        path = value.get("file_path")
        if not path:
            return str(value.get("id", value.get("$id", value)))
    else:
        path = getattr(value, "file_path", None)
        if not path:
            return str(getattr(value, "id", value))
            
    if path and isinstance(path, str) and path.startswith("/media/"):
        return get_media_url(path)
    return path

# The "Thumbnail" Type
Thumbnail = Annotated[
    Optional[Link["Attachment"]], 
    Field(default=None),
    PlainSerializer(serialize_attachment, return_type=Optional[str], when_used="json")
]

def Attechment(foldername: str = "general", label: str = "Attachment") -> Any:
    """
    Factory for specific attachment fields with folder constraints.
    """
    return Annotated[
        Optional[Link["Attachment"]],
        Field(default=None, description=f"Enter {label}", json_schema_extra={"folder": foldername}),
        PlainSerializer(serialize_attachment, return_type=Optional[str], when_used="json")
    ]


# --- Auth Fields ---

# The "Owner" Type
Owner = Annotated[
    Link["User"], 
    Field(description="Owner of the document")
]


# --- Shortcuts ---

def Slug(depend: str = "name", max_length: int = 255) -> Any:
    """
    Returns an Annotated type for a slug field that depends on another field.
    """
    return Annotated[
        Optional[str], 
        Field(default=None, max_length=max_length, json_schema_extra={"slugify": True, "populate_from": depend})
    ]

# Generic Link Factory (for custom links)
def Connect(to: Any, label: str = "Connection") -> Any:
    """
    A generic factory to create a Link[to] field.
    """
    return Annotated[
        Link[to],
        Field(description=f"Connect to {label}")
    ]

import os
import math
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Request, Depends, HTTPException, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict # Added for pydantic models
from ..core.models import User
from ..utils import PasswordManager, TokenManager
from .site import admin_site

# Define INTERNAL_FIELDS globally
INTERNAL_FIELDS = ["id", "_id", "revision_id", "created_at", "created_by", "updated_at", "updated_by", "is_deleted", "deleted_at", "deleted_by"]

def get_model_fields(model):
    """
    Returns all Pydantic model_fields including those inherited from parent classes.
    model.model_fields only returns fields declared directly on the class.
    """
    all_fields = {}
    # Walk MRO in reverse so subclass fields override parent fields
    for cls in reversed(model.__mro__):
        if hasattr(cls, "model_fields") and isinstance(cls.model_fields, dict):
            all_fields.update(cls.model_fields)
    return all_fields

router = APIRouter(prefix="/admin")

# Get absolute path to templates
template_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=template_dir)

# Custom Filters
def nice_title(value: str) -> str:
    if not value: return ""
    return value.replace("_", " ").title()

def filesize(value) -> str:
    """Format raw bytes into human-readable size (B, KB, MB, GB)."""
    try:
        size = float(value)
    except (TypeError, ValueError):
        return str(value) if value else "—"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(size) < 1024.0:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"

templates.env.filters["nice_title"] = nice_title
templates.env.filters["filesize"] = filesize

# Helper to check if logged in via Cookie
async def get_admin_user(request: Request) -> Optional[User]:
    token = request.cookies.get("admin_session")
    if not token:
        return None
    
    try:
        # Verify token and get user (simplified validation)
        payload = TokenManager.decode_token(token)
        if not payload:
            return None
            
        user_id = payload.get("sub")
        sid = payload.get("sid")
        
        # ideally verify session exists/is active too
        user = await User.get(user_id)
        if user and user.is_superuser:
            return user
    except Exception:
        pass
    return None

@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(request: Request, user: Optional[User] = Depends(get_admin_user)):
    if not user:
        return RedirectResponse(url="/admin/login")
    
    models = admin_site.get_registered_models()
    
    # Calculate Database Stats
    db_stats = {
        "total_models": len(models),
        "total_documents": 0,
        "total_size_mb": 0.0
    }
    
    model_stats = {}
    for m in models:
        try:
            model = m["model"]
            
            # Safely get Count
            try:
                count = await model.find_all().count()
            except Exception:
                count = 0
            
            # Safely get Size
            size_mb = 0.0
            try:
                db = model.get_settings().pymongo_db
                stats = await db.command("collStats", model.get_collection_name())
                size_bytes = stats.get("totalSize") or stats.get("storageSize") or stats.get("size") or 0
                size_mb = size_bytes / (1024 * 1024)
            except Exception:
                pass # E.g. Atlas Serverless permission denied
            
            model_stats[m["name"]] = {"count": count, "size_mb": round(size_mb, 2)}
            db_stats["total_documents"] += count
            db_stats["total_size_mb"] += size_mb
        except Exception as e:
            import traceback
            traceback.print_exc()
            model_stats[m["name"]] = {"count": 0, "size_mb": 0.0}
            
    db_stats["total_size_mb"] = round(db_stats["total_size_mb"], 2)

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "models": models,
        "user": user,
        "now": datetime.now(timezone.utc),
        "db_stats": db_stats,
        "model_stats": model_stats
    })

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    superuser_count = await User.find(User.is_superuser == True).count()
    return templates.TemplateResponse("login.html", {
        "request": request,
        "superuser_exists": superuser_count > 0,
        "error": None
    })

@router.post("/login")
async def login_handle(
    request: Request,
    email: str = Form(...),
    password: str = Form(...)
):
    superuser_count = await User.find(User.is_superuser == True).count()
    
    # 1. Handle Superuser Creation if none exists
    if superuser_count == 0:
        hashed_pw = PasswordManager.hash_password(password)
        new_superuser = User(
            email=email,
            full_name=email.split('@')[0].title() or "Admin",
            hashed_password=hashed_pw,
            is_superuser=True,
            is_staff=True,
            is_active=True
        )
        await new_superuser.insert()
        user = new_superuser
    else:
        # 2. Normal Login via AuthService
        # Fetch user by email manually since AuthService expects email for standard login
        user = await User.find_one(User.email == email)
        
        if not user or not PasswordManager.verify_password(password, user.hashed_password):
             return templates.TemplateResponse("login.html", {
                "request": request,
                "superuser_exists": True,
                "error": "Invalid username or password"
            })
            
        if not user.is_superuser:
            return templates.TemplateResponse("login.html", {
                "request": request,
                "superuser_exists": True,
                "error": "Access denied. Superuser only."
            })

    # Create Session via AuthService
    from ..auth.service import AuthService
    auth_service = AuthService(request)
    
    # We use a manual session creation here because we already verified password
    session_data = await auth_service.create_session(
        user=user, 
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None
    )
    
    access_token = session_data["access_token"]

    response = RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="admin_session", value=access_token, httponly=True)
    return response

@router.get("/logout")
async def logout(request: Request):
    response = RedirectResponse(url="/admin/login")
    response.delete_cookie("admin_session")
    
    # Ideally invalidate session in DB too
    token = request.cookies.get("admin_session")
    if token:
         try:
            payload = TokenManager.decode_token(token)
            if payload:
                sid = payload.get("sid")
                from ..auth.service import AuthService
                auth_service = AuthService(request)
                await auth_service.logout(sid)
         except: pass
         
    return response

@router.get("/{model_name}", response_class=HTMLResponse)
async def model_list(
    request: Request, 
    model_name: str, 
    page: int = 1,
    user: Optional[User] = Depends(get_admin_user)
):
    if not user:
        return RedirectResponse(url="/admin/login")
    
    config = admin_site.get_model_config(model_name)
    if not config:
        raise HTTPException(status_code=404, detail="Model not found")
    
    model = config["model"]
    limit = 20
    skip = (page - 1) * limit
    
    query = {}
    if "is_deleted" in get_model_fields(model):
        query["is_deleted"] = {"$ne": True}
        
    total_count = await model.find(query).count()
    
    from ..core.repository import BeanieRepository
    repo = BeanieRepository()
    repo.document_class = model
    populate_fields = BeanieRepository.detect_populate_fields(model)
    
    sort_query = [("created_at", -1)] if "created_at" in get_model_fields(model) else None
    items = await repo.get_all(query, skip=skip, limit=limit, sort=sort_query, populate_fields=populate_fields)
    total_pages = math.ceil(total_count / limit) if limit > 0 else 1
    
    field_links = {}
    if populate_fields:
        for fname, fconfig in populate_fields.items():
            if isinstance(fconfig, dict) and "collection" in fconfig:
                coll = fconfig["collection"]
                for m_config in admin_site.get_registered_models():
                    if hasattr(m_config["model"], "Settings") and getattr(m_config["model"].Settings, "name", None) == coll:
                        field_links[fname] = m_config["name"]
                        break
    
    return templates.TemplateResponse("model_list.html", {
        "request": request,
        "model_name": model_name,
        "items": items,
        "total_count": total_count,
        "current_page": page,
        "total_pages": total_pages,
        "page_size": limit,
        "models": admin_site.get_registered_models(),
        "user": user,
        "now": datetime.now(timezone.utc),
        "field_links": field_links,
        "model_fields": get_model_fields(model),
        "internal_fields": INTERNAL_FIELDS
    })

@router.get("/{model_name}/create", response_class=HTMLResponse)
async def model_create_page(
    request: Request,
    model_name: str,
    user: Optional[User] = Depends(get_admin_user)
):
    if not user:
        return RedirectResponse(url="/admin/login")
    
    config = admin_site.get_model_config(model_name)
    if not config:
        raise HTTPException(status_code=404, detail="Model not found")
    
    model = config["model"]
    
    from ..core.repository import BeanieRepository
    populate_fields = BeanieRepository.detect_populate_fields(model)
    
    link_options = {}
    field_links = {}
    if populate_fields:
        for fname, fconfig in populate_fields.items():
            if isinstance(fconfig, dict) and "collection" in fconfig:
                coll = fconfig["collection"]
                for m_config in admin_site.get_registered_models():
                    if hasattr(m_config["model"], "Settings") and getattr(m_config["model"].Settings, "name", None) == coll:
                        target_model_name = m_config["name"]
                        target_model = m_config["model"]
                        field_links[fname] = target_model_name
                        break
                        
    return templates.TemplateResponse("model_create.html", {
        "request": request,
        "model_name": model_name,
        "model_fields": get_model_fields(model),
        "internal_fields": INTERNAL_FIELDS, 
        "models": admin_site.get_registered_models(),
        "user": user,
        "now": datetime.now(timezone.utc),
        "field_links": field_links
    })

@router.post("/{model_name}/create")
async def model_create_handle(
    request: Request,
    model_name: str,
    user: Optional[User] = Depends(get_admin_user)
):
    if not user:
        return RedirectResponse(url="/admin/login")
    
    config = admin_site.get_model_config(model_name)
    if not config:
        raise HTTPException(status_code=404, detail="Model not found")
    
    model = config["model"]
    form_data = await request.form()
    
    # Filter and cast form data
    data = {}
    
    for key, field in get_model_fields(model).items():
        if key in INTERNAL_FIELDS:
            continue
            
        is_list = "list" in str(field.annotation).lower()
        is_link = "link" in str(field.annotation).lower()
        
        if key in form_data:
            val = form_data.getlist(key) if is_list else form_data[key]
            
            if is_list:
                if not val or (len(val) == 1 and not val[0]):
                    val = []
            elif not val and field.annotation != bool:
                continue
                
            # Simple type casting
            if field.annotation == bool:
                val = val.lower() == "true" if isinstance(val, str) else bool(val)
            elif field.annotation == int and not is_list:
                try: val = int(val)
                except: pass
            elif field.annotation == float and not is_list:
                try: val = float(val)
                except: pass
                
            if model_name == "User" and key == "hashed_password" and val:
                from ..utils import PasswordManager
                if isinstance(val, str) and not val.startswith("$argon2"):
                    val = PasswordManager.hash_password(val)
                    
            if is_link and val:
                from ..core.repository import BeanieRepository
                from bson import ObjectId
                from bson.dbref import DBRef
                populate_fields = BeanieRepository.detect_populate_fields(model)
                if key in populate_fields:
                    collection_name = populate_fields[key].get("collection")
                    if collection_name:
                        if is_list and isinstance(val, list):
                            new_val = []
                            for item_id in val:
                                try:
                                    if len(str(item_id)) == 24:
                                        new_val.append(DBRef(collection=collection_name, id=ObjectId(item_id)))
                                except: pass
                            val = new_val
                        elif isinstance(val, str) and len(val) == 24:
                            try:
                                val = DBRef(collection=collection_name, id=ObjectId(val))
                            except: pass
                    
            data[key] = val
            
    try:
        instance = model(**data)
        if hasattr(instance, "created_by"):
            instance.created_by = str(user.id)
        await instance.insert()
        return RedirectResponse(url=f"/admin/{model_name}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        # For now simple error, ideally re-render with error
        raise HTTPException(status_code=400, detail=f"Creation failed: {str(e)}")

@router.post("/{model_name}/delete_all")
async def model_delete_all_handle(
    request: Request,
    model_name: str,
    user: Optional[User] = Depends(get_admin_user)
):
    if not user or not user.is_superuser:
        return RedirectResponse(url="/admin/login")
    
    config = admin_site.get_model_config(model_name)
    if not config: raise HTTPException(status_code=404)
    
    model = config["model"]
    # Delete All
    await model.delete_all()
    
    return RedirectResponse(url=f"/admin/{model_name}", status_code=status.HTTP_303_SEE_OTHER)

@router.get("/{model_name}/{pk}", response_class=HTMLResponse)
async def model_detail(
    request: Request,
    model_name: str,
    pk: str,
    user: Optional[User] = Depends(get_admin_user)
):
    if not user:
        return RedirectResponse(url="/admin/login")
    
    config = admin_site.get_model_config(model_name)
    if not config:
        raise HTTPException(status_code=404, detail="Model not found")
    
    model = config["model"]
    
    from bson import ObjectId
    from ..core.repository import BeanieRepository
    
    repo = BeanieRepository()
    repo.document_class = model
    populate_fields = BeanieRepository.detect_populate_fields(model)
    
    # query
    query = {"_id": pk}
    try:
        if len(str(pk)) == 24:
            query = {"_id": ObjectId(pk)}
    except:
        pass
        
    item_dict = await repo.get_one(query, populate_fields=populate_fields)
    
    
    if not item_dict:
        raise HTTPException(status_code=404, detail="Record not found")

    field_links = {}
    link_options = {}
    if populate_fields:
        for fname, fconfig in populate_fields.items():
            if isinstance(fconfig, dict) and "collection" in fconfig:
                coll = fconfig["collection"]
                for m_config in admin_site.get_registered_models():
                    if hasattr(m_config["model"], "Settings") and getattr(m_config["model"].Settings, "name", None) == coll:
                        target_model_name = m_config["name"]
                        target_model = m_config["model"]
                        field_links[fname] = target_model_name
                        
                        # Fetch ONLY the selected items to pre-populate the dropdown
                        try:
                            val = item_dict.get(fname)
                            if not val:
                                break
                                
                            val_list = val if isinstance(val, list) else [val]
                            val_list = [v for v in val_list if v]
                            
                            if not val_list:
                                break
                                
                            from bson import ObjectId
                            ids_to_fetch = []
                            for v in val_list:
                                vid = v.id if hasattr(v, "id") else v.get("id") if isinstance(v, dict) else v
                                try:
                                    if isinstance(vid, (str, ObjectId)):
                                        ids_to_fetch.append(ObjectId(str(vid)))
                                except: pass
                                
                            items = await target_model.find({"_id": {"$in": ids_to_fetch}}).to_list()
                            
                            options = []
                            for it in items:
                                label = str(it.id)
                                for display_field in ["name", "title", "full_name", "username", "email", "filename", "question"]:
                                    test_val = getattr(it, display_field, None)
                                    if test_val:
                                        label = f"{test_val} ({it.id})"
                                        break
                                options.append({"id": str(it.id), "label": label})
                            link_options[fname] = options
                        except:
                            pass
                        break

    return templates.TemplateResponse("model_detail.html", {
        "request": request,
        "model_name": model_name,
        "item": item_dict,
        "model_fields": get_model_fields(model),
        "models": admin_site.get_registered_models(),
        "user": user,
        "now": datetime.now(timezone.utc),
        "field_links": field_links,
        "link_options": link_options,
        "internal_fields": INTERNAL_FIELDS
    })

@router.post("/{model_name}/{pk}")
async def model_update_handle(
    request: Request,
    model_name: str,
    pk: str,
    user: Optional[User] = Depends(get_admin_user)
):
    if not user:
        return RedirectResponse(url="/admin/login")
    
    config = admin_site.get_model_config(model_name)
    if not config:
        raise HTTPException(status_code=404, detail="Model not found")
    
    model = config["model"]
    item = await model.find_one({"_id": pk})
    if not item:
        from bson import ObjectId
        try:
            item = await model.find_one({"_id": ObjectId(pk)})
        except: pass
        
    if not item:
        raise HTTPException(status_code=404, detail="Record not found")

    form_data = await request.form()
    update_data = {}
    
    for key, field in get_model_fields(model).items():
        if key in INTERNAL_FIELDS:
            continue
            
        is_list = "list" in str(field.annotation).lower()
        is_link = "link" in str(field.annotation).lower()

        if key in form_data:
            val = form_data.getlist(key) if is_list else form_data[key]
            
            if is_list:
                if not val or (len(val) == 1 and not val[0]):
                    val = []
            elif not val and field.annotation != bool:
                continue

            if field.annotation == bool:
                val = val.lower() == "true" if isinstance(val, str) else bool(val)
            elif field.annotation == int and not is_list:
                try: val = int(val)
                except: pass
            elif field.annotation == float and not is_list:
                try: val = float(val)
                except: pass

            if model_name == "User" and key == "hashed_password" and val:
                from ..utils import PasswordManager
                if isinstance(val, str) and not val.startswith("$argon2"):
                    val = PasswordManager.hash_password(val)

            if is_link and val:
                from ..core.repository import BeanieRepository
                from bson import ObjectId
                from bson.dbref import DBRef
                populate_fields = BeanieRepository.detect_populate_fields(model)
                if key in populate_fields:
                    collection_name = populate_fields[key].get("collection")
                    if collection_name:
                        if is_list and isinstance(val, list):
                            new_val = []
                            for item_id in val:
                                try:
                                    if len(str(item_id)) == 24:
                                        new_val.append(DBRef(collection=collection_name, id=ObjectId(item_id)))
                                except: pass
                            val = new_val
                        elif isinstance(val, str) and len(val) == 24:
                            try:
                                val = DBRef(collection=collection_name, id=ObjectId(val))
                            except: pass

            update_data[key] = val

    try:
        if hasattr(item, "updated_at"):
            update_data["updated_at"] = datetime.now(timezone.utc)
        if hasattr(item, "updated_by"):
            update_data["updated_by"] = str(user.id)
            
        await item.set(update_data)
        return RedirectResponse(url=f"/admin/{model_name}/{pk}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Update failed: {str(e)}")

@router.get("/{model_name}/{pk}/delete")
async def model_delete_handle(
    request: Request,
    model_name: str,
    pk: str,
    user: Optional[User] = Depends(get_admin_user)
):
    if not user or not user.is_superuser:
        return RedirectResponse(url="/admin/login")
    
    config = admin_site.get_model_config(model_name)
    if not config: raise HTTPException(status_code=404)
    
    model = config["model"]
    try:
        item = await model.get(pk)
    except Exception:
        item = None
        
    if not item:
        from bson import ObjectId
        try:
            item = await model.find_one({"_id": ObjectId(pk)})
        except Exception:
            pass
            
    if item:
        if hasattr(item, "is_deleted"):
            await item.set({"is_deleted": True, "deleted_at": datetime.now(timezone.utc)})
        else:
            await item.delete()
            
    return RedirectResponse(url=f"/admin/{model_name}", status_code=status.HTTP_303_SEE_OTHER)

@router.get("/api/search/{target_model}")
async def admin_api_search(
    request: Request,
    target_model: str,
    q: Optional[str] = "",
    page: int = 1,
    user: Optional[User] = Depends(get_admin_user)
):
    """
    Generic AJAX endpoint that returns Select2 formatted options manually paginated.
    """
    if not user:
         raise HTTPException(status_code=401)
         
    config = admin_site.get_model_config(target_model)
    if not config: return {"results": [], "pagination": {"more": False}}
    
    model = config["model"]
    limit = 10
    skip = (page - 1) * limit
    
    query = {}
    if "is_deleted" in get_model_fields(model):
        query["is_deleted"] = {"$ne": True}
        
    if q:
        search_params = []
        for field_name in ["name", "title", "full_name", "username", "email", "filename", "question", "subject"]:
            if field_name in get_model_fields(model):
                search_params.append({field_name: {"$regex": q, "$options": "i"}})
        if search_params:
            if "is_deleted" in query:
                query = {"$and": [{"is_deleted": {"$ne": True}}, {"$or": search_params}]}
            else:
                query = {"$or": search_params}
            
    items = await model.find(query).skip(skip).limit(limit).to_list()
    total = await model.find(query).count()
    
    results = []
    for it in items:
        label = str(it.id)
        for display_field in ["name", "title", "full_name", "username", "email", "filename", "question"]:
            val = getattr(it, display_field, None)
            if val:
                label = f"{val} ({it.id})"
                break
        results.append({"id": str(it.id), "text": label})
        
    return {
        "results": results,
        "pagination": {
            "more": (skip + limit) < total
        }
    }



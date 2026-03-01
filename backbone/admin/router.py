import os
import math
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Request, Depends, HTTPException, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from ..core.models import User
from ..utils import PasswordManager, TokenManager
from .site import admin_site

router = APIRouter(prefix="/admin")

# Get absolute path to templates
template_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=template_dir)

# Custom Filters
def nice_title(value: str) -> str:
    if not value: return ""
    return value.replace("_", " ").title()

templates.env.filters["nice_title"] = nice_title

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
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "models": models,
        "user": user,
        "now": datetime.now(timezone.utc)
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
            full_name="Admin User",
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
    
    total_count = await model.find_all().count()
    
    from ..core.repository import BeanieRepository
    repo = BeanieRepository()
    repo.document_class = model
    populate_fields = BeanieRepository.detect_populate_fields(model)
    
    items = await repo.get_all({}, skip=skip, limit=limit, populate_fields=populate_fields)
    total_pages = math.ceil(total_count / limit)
    
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
        "now": datetime.now(timezone.utc)
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
    return templates.TemplateResponse("model_create.html", {
        "request": request,
        "model_name": model_name,
        "model_fields": model.model_fields,
        "models": admin_site.get_registered_models(),
        "user": user,
        "now": datetime.now(timezone.utc)
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
    for key, field in model.model_fields.items():
        if key in form_data and form_data[key]:
            val = form_data[key]
            # Simple type casting
            if field.annotation == bool:
                val = val.lower() == "true"
            elif field.annotation == int:
                val = int(val)
            elif field.annotation == float:
                val = float(val)
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

    return templates.TemplateResponse("model_detail.html", {
        "request": request,
        "model_name": model_name,
        "item": item_dict,
        "model_fields": model.model_fields,
        "models": admin_site.get_registered_models(),
        "user": user,
        "now": datetime.now(timezone.utc)
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
    for key, field in model.model_fields.items():
        if key in ["id", "_id", "created_at", "created_by"]:
            continue
            
        if key in form_data:
            val = form_data[key]
            if field.annotation == bool:
                val = val.lower() == "true"
            elif field.annotation == int:
                val = int(val)
            elif field.annotation == float:
                val = float(val)
            
            # If the user submitted a JSON string for a Link field, extract ID
            if "Link" in str(field.annotation) and isinstance(val, str) and val.startswith("{"):
                import json
                try:
                    parsed = json.loads(val)
                    if isinstance(parsed, dict) and "id" in parsed:
                        val = parsed["id"]
                except:
                    pass
            elif "Link" in str(field.annotation) and isinstance(val, str) and val.startswith("["):
                import json
                try:
                    parsed = json.loads(val)
                    if isinstance(parsed, list):
                        new_val = []
                        for el in parsed:
                            if isinstance(el, dict) and "id" in el:
                                new_val.append(el["id"])
                            else:
                                new_val.append(el)
                        val = new_val
                except:
                    pass

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
    item = await model.find_one({"_id": pk})
    if not item:
        from bson import ObjectId
        try: item = await model.find_one({"_id": ObjectId(pk)})
        except: pass
        
    if item:
        if hasattr(item, "is_deleted"):
            await item.set({"is_deleted": True, "deleted_at": datetime.now(timezone.utc)})
        else:
            await item.delete()
            
    return RedirectResponse(url=f"/admin/{model_name}", status_code=status.HTTP_303_SEE_OTHER)



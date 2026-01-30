from fastapi import APIRouter, HTTPException, status, Depends
from .db import db
from .utils import SecurityUtils, JWTUtils
from .schemas import UserSchema, UserOut
from .dependencies import get_current_user
from typing import Dict, Any

class AuthRouter:
    def __init__(self, prefix: str = "/auth", tags: list = ["Auth"]):
        self.router = APIRouter(prefix=prefix, tags=tags)
        self.collection = db["users"]
        self._register_routes()

    def _register_routes(self):
        @self.router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
        async def register(user: UserSchema):
            existing_user = await self.collection.find_one({"email": user.email})
            if existing_user:
                raise HTTPException(status_code=400, detail="Email already registered")
            
            user_dict = user.model_dump(by_alias=True)
            user_dict["hashed_password"] = SecurityUtils.hash_password(user_dict["hashed_password"])
            
            result = await self.collection.insert_one(user_dict)
            created_user = await self.collection.find_one({"_id": result.inserted_id})
            return created_user

        @self.router.post("/login")
        async def login(credentials: Dict[str, str]):
            email = credentials.get("email")
            password = credentials.get("password")
            
            user_data = await self.collection.find_one({"email": email})
            if not user_data or not SecurityUtils.verify_password(password, user_data["hashed_password"]):
                raise HTTPException(status_code=401, detail="Invalid credentials")
            
            token = JWTUtils.create_access_token(data={"sub": str(user_data["_id"]), "email": user_data["email"]})
            return {"access_token": token, "token_type": "bearer"}
        
        @self.router.get("/me", response_model=UserOut)
        async def me(user: UserOut = Depends(get_current_user)):
            """
            Fetch current authenticated user information.
            """
            return user

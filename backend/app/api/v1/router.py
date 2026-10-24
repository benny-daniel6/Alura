from fastapi import APIRouter
from app.api.v1.endpoints import auth, users, wardrobe, outfits, stylist

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users.router, prefix="/users", tags=["Users & Preferences"])
api_router.include_router(wardrobe.router, prefix="/wardrobe", tags=["Digital Wardrobe"])
api_router.include_router(outfits.router, prefix="/outfits", tags=["Outfit Studio"])
api_router.include_router(stylist.router, prefix="/stylist", tags=["AI Stylist"])

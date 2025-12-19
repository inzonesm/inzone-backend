from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class Item(BaseModel):
    category: Optional[str] = None  # e.g. hoodie, jeans, sneakers, etc.
    color: Optional[str] = None  # e.g. white, blue, black, etc.
    notes: Optional[str] = None  # any other specified details

class Clothing(BaseModel):
    top: Optional[Item] = None
    bottom: Optional[Item] = None
    shoes: Optional[Item] = None
    outerwear: Optional[Item] = None
    accessories: List[str] = Field(default_factory=list)

class AvatarSpec(BaseModel):
    style: Dict[str, Optional[str]]
    species: str  # human or non humanoid
    body: Dict[str, Optional[str]]  # skin tone, build, height, etc.
    hair: Dict[str, Optional[str]]  # color, style, length
    clothing: Clothing
    palette: List[str] = Field(default_factory=list)
    pose: str
    camera: str
    notes: List[str] = Field(default_factory=list)
    confidence: Dict[str, float] = Field(default_factory=dict)
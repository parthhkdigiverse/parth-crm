from pydantic import BaseModel, ConfigDict, model_validator, BeforeValidator
from beanie import PydanticObjectId as BeaniePydanticObjectId
from typing import Any, Annotated
from bson import ObjectId

def validate_object_id(v: Any) -> Any:
    if isinstance(v, (ObjectId, BeaniePydanticObjectId)):
        return str(v)
    return v

# Redefine PydanticObjectId for reliable Pydantic V2 response serialization
# This Annotated type ensures any ObjectId is converted to a string before validation.
PydanticObjectId = Annotated[str, BeforeValidator(validate_object_id)]

class MongoBaseSchema(BaseModel):
    """
    Base schema for all Pydantic models in the FastAPI app.
    Ensures compatibility with MongoDB's _id and Beanie's ObjectId in Pydantic V2.
    """
    model_config = ConfigDict(
        populate_by_name=True,        # Allows using standard 'id' instead of forcing '_id'
        from_attributes=True,         # Replaces V1's orm_mode=True
        arbitrary_types_allowed=True, # Required for PydanticObjectId if it remains a non-builtin
    )

    @model_validator(mode='before')
    @classmethod
    def _convert_ids(cls, data: Any) -> Any:
        """
        Force-converts dictionary-based IDs.
        """
        if isinstance(data, dict):
            if "_id" in data and "id" not in data:
                data["id"] = data["_id"]
            
            for k, v in data.items():
                if isinstance(v, ObjectId):
                    data[k] = str(v)
        return data
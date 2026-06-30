from typing import Any, Optional
from pydantic import BaseModel, Field


class Config(BaseModel):
    model: Any = Field(...)
    output_file: Optional[str] = Field(None)
    context_ids: Optional[list[int]] = Field(None)
    functions_format: Optional[dict[str, list[dict[str,
                                                   str | list[int]
                                                   ]]]] = Field(None)
    numbers_vocab: Optional[list[int]] = Field(None)
    token_to_id: Optional[dict[str, int]] = Field(None)
    id_to_token: Optional[dict[int, str]] = Field(None)
    function_name_encodings: Optional[dict[str, list[int]]] = Field(None)
    first_token_map: Optional[list[str]] = Field(None)

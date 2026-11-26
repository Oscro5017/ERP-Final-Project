"""Shared response pieces."""
from pydantic import BaseModel, model_serializer


class DecryptionStatusResponse(BaseModel):
    decrypt_failed: bool = False

    @model_serializer(mode="wrap")
    def serialize_decryption_status(self, handler):
        data = handler(self)
        if not self.decrypt_failed:
            data.pop("decrypt_failed", None)
        return data

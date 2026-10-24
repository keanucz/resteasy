"""Schemas for the resident's profile photo."""

from pydantic import BaseModel


class ResidentPhoto(BaseModel):
    """The photo's public link, versioned so a new photo shows straight away; None when there is none."""

    url: str | None


class PhotoUpload(BaseModel):
    """A checked photo upload: a JPEG, PNG or WebP image within the size limit."""

    content: bytes
    content_type: str

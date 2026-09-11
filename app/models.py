from sqlalchemy import Column, Integer, String, Text
from app.db import Base


class CodeChunk(Base):
    __tablename__ = "code_chunks"

    id = Column(Integer, primary_key=True, index=True)
    text = Column(Text, nullable=False)
    file_path = Column(String, nullable=True)
    language = Column(String, nullable=True)
    function_name = Column(String, nullable=True)
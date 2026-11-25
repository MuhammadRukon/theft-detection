from pydantic import BaseModel


def format_sse(event: str, data: BaseModel, id: str | None = None) -> str:
    head = f"id: {id}\n" if id else ""
    return f"{head}event: {event}\ndata: {data.model_dump_json(by_alias=True)}\n\n"

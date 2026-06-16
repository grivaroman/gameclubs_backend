"""Локальный запуск сервера с dev-шимами совместимости.

Шимы нужны потому, что requirements.txt не пинит версии, и pip ставит самые
свежие fastapi/starlette/bcrypt, несовместимые с кодом приложения:
  * bcrypt 5.x ломает самотест passlib 1.7.4 (см. local_bcrypt_fix);
  * starlette>=1.0 требует TemplateResponse(request, name, ...), а приложение
    зовёт по-старому TemplateResponse(name, context).
На проде правильнее запинить версии в requirements.txt либо обновить вызовы.
"""
import local_bcrypt_fix  # noqa: F401  — до passlib

# --- compat: legacy TemplateResponse(name, context) -> (request, name, context) ---
from starlette.templating import Jinja2Templates

_orig_template_response = Jinja2Templates.TemplateResponse


def _template_response_compat(self, *args, **kwargs):
    if args and isinstance(args[0], str):
        name = args[0]
        context = args[1] if len(args) > 1 else kwargs.pop("context", None) or {}
        request = context.get("request")
        return _orig_template_response(self, request, name, context, *args[2:], **kwargs)
    return _orig_template_response(self, *args, **kwargs)


Jinja2Templates.TemplateResponse = _template_response_compat

import uvicorn

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)

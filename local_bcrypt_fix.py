"""Локальный dev-шим совместимости bcrypt 5.x с passlib 1.7.4.

passlib 1.7.4 не обновляется; его самотест бэкенда bcrypt падает на bcrypt>=4.1
(новый bcrypt бросает исключение на пароль >72 байт вместо обрезки). bcrypt по
дизайну использует только первые 72 байта, поэтому обрезка эквивалентна.

Импортируется ЯВНО (run_local.py, seed_local.py) — на проде же правильнее
запинить bcrypt<4.1 в requirements.txt.
"""
try:
    import bcrypt as _b

    if not hasattr(_b, "__about__"):
        _hashpw, _checkpw = _b.hashpw, _b.checkpw

        def _trunc(pw):
            if isinstance(pw, str):
                pw = pw.encode()
            return pw[:72]

        _b.hashpw = lambda pw, salt: _hashpw(_trunc(pw), salt)
        _b.checkpw = lambda pw, h: _checkpw(_trunc(pw), h)

        class _About:
            __version__ = getattr(_b, "__version__", "5.0.0")

        _b.__about__ = _About
except Exception:
    pass

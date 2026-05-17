set -eu

alembic upgrade head

exec "$@"

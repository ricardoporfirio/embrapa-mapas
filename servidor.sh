#!/usr/bin/env bash
# Execute com: bash servidor.sh start|stop|restart|status|logs
set -Eeuo pipefail
set +m
umask 077

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="$PROJECT_DIR/runtime/server"
PID_FILE="$STATE_DIR/server.pid"
LOG_FILE="$STATE_DIR/server.log"
ACTION="${1:-start}"

usage() { printf 'Uso: bash servidor.sh {start|stop|restart|status|logs}\n'; }
case "$ACTION" in
    -h|--help|help) usage; exit 0 ;;
    start|stop|restart|status|logs) ;;
    *) usage >&2; exit 2 ;;
esac
if [[ "$(uname -s)" != Linux ]]; then
    printf 'Execute este script no servidor Linux.\n' >&2
    exit 1
fi
cd -- "$PROJECT_DIR"
mkdir -p -- "$STATE_DIR"

# Confere o instante de criação para não confundir um PID reutilizado.
process_start() {
    local stat rest
    [[ -r "/proc/$1/stat" ]] || return 1
    stat="$(cat -- "/proc/$1/stat")" || return 1
    rest="${stat##*) }"
    local -a fields
    read -r -a fields <<< "$rest"
    [[ "${fields[0]}" != Z ]] || return 1
    printf '%s\n' "${fields[19]}"
}

running() {
    local saved_start current_start
    [[ -f "$PID_FILE" ]] || return 1
    read -r SERVER_PID saved_start < "$PID_FILE" || return 1
    [[ "$SERVER_PID" =~ ^[0-9]+$ && "$saved_start" =~ ^[0-9]+$ ]] || return 1
    (( SERVER_PID > 1 )) || return 1
    kill -0 "$SERVER_PID" 2>/dev/null || return 1
    current_start="$(process_start "$SERVER_PID")" || return 1
    [[ "$current_start" == "$saved_start" ]]
}

start_server() {
    if running; then
        printf 'Servidor já está rodando (PID %s).\n' "$SERVER_PID"
        return 0
    fi
    local uv_command
    uv_command="$(command -v uv || true)"
    if [[ -z "$uv_command" && -x "$HOME/.local/bin/uv" ]]; then
        uv_command="$HOME/.local/bin/uv"
    fi
    if [[ -z "$uv_command" ]]; then
        printf 'Instale o uv: https://docs.astral.sh/uv/getting-started/installation/\n' >&2
        return 1
    fi
    command -v nohup >/dev/null
    command -v setsid >/dev/null
    "$uv_command" sync --locked
    if [[ ! -f .env ]]; then
        .venv/bin/python - <<'PY'
import secrets
from pathlib import Path
with Path('.env').open('x', encoding='utf-8') as config:
    config.write('SECRET_KEY=' + secrets.token_hex(32) + '\nAPP_ENV=development\nHOST=127.0.0.1\nPORT=5001\n')
PY
        printf 'Arquivo .env criado com chave de sessão aleatória.\n'
    fi
    .venv/bin/python -c 'import app' >> "$LOG_FILE" 2>&1 || {
        printf 'Falha na preparação. Consulte: %s\n' "$LOG_FILE" >&2
        tail -n 30 -- "$LOG_FILE" >&2
        return 1
    }
    # setsid separa a sessão; nohup ignora a desconexão; os fluxos não usam o SSH.
    # Controle de jobs desativado garante que setsid preserve o PID do filho.
    nohup setsid "$PROJECT_DIR/.venv/bin/python" -u "$PROJECT_DIR/app.py" \
        </dev/null >> "$LOG_FILE" 2>&1 9>&- &
    local pid=$! started
    if ! started="$(process_start "$pid")"; then
        printf 'Falha ao iniciar. Consulte: %s\n' "$LOG_FILE" >&2
        return 1
    fi
    printf '%s %s\n' "$pid" "$started" > "$PID_FILE"
    sleep 3
    if ! running; then
        rm -f -- "$PID_FILE"
        printf 'O servidor encerrou durante a inicialização.\n' >&2
        tail -n 30 -- "$LOG_FILE" >&2
        return 1
    fi
    printf 'Processo iniciado (PID %s). Você pode fechar o SSH.\nLog: %s\n' "$SERVER_PID" "$LOG_FILE"
}

stop_server() {
    if ! running; then
        rm -f -- "$PID_FILE"
        printf 'Servidor está parado.\n'
        return 0
    fi
    kill -TERM "$SERVER_PID"
    for ((attempt=0; attempt<30; attempt++)); do
        if ! running; then
            rm -f -- "$PID_FILE"
            printf 'Servidor encerrado.\n'
            return 0
        fi
        sleep 1
    done
    printf 'O processo ainda está encerrando. Consulte os logs.\n' >&2
    return 1
}

# Uma operação de controle por vez; o servidor não herda o bloqueio.
if [[ "$ACTION" != logs ]]; then
    command -v flock >/dev/null
    exec 9> "$STATE_DIR/control.lock"
    flock -n 9 || { printf 'Outro comando de controle está em andamento.\n' >&2; exit 1; }
fi
case "$ACTION" in
    start) start_server ;;
    stop) stop_server ;;
    restart) stop_server; start_server ;;
    status)
        if running; then
            printf 'Servidor rodando (PID %s).\n' "$SERVER_PID"
        else
            printf 'Servidor parado.\n'
            exit 1
        fi
        ;;
    logs) touch -- "$LOG_FILE"; exec tail -n 100 -F -- "$LOG_FILE" ;;
esac

#!/bin/bash
# ESTE ES EL BUENO - El único que reinicia si hay un crash.

DIR="$(cd -P "$( dirname "${BASH_SOURCE[0]}" )" && pwd)"
cd "$DIR"

export TERM=xterm-256color
export TERMINFO=/usr/share/terminfo

chmod +x ./bin/php7/bin/php 2>/dev/null || true

if [ -f "./bin/php7/bin/php" ]; then
    PHP_BINARY="./bin/php7/bin/php"
else
    PHP_BINARY="php"
fi

if [ -f "PocketMine-MP.phar" ]; then
    PMMP_FILE="PocketMine-MP.phar"
else
    PMMP_FILE="src/pocketmine/PocketMine.php"
fi

# Bucle infinito para que si se cae, se levante solo.
while true; do
    "$PHP_BINARY" "$PMMP_FILE" --enable-ansi
    echo "[start.sh] El servidor se detuvo. Reiniciando en 5 segundos..."
    sleep 5
done

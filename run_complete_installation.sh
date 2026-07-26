#!/bin/sh

printf "Setting up python build environment..."
python -m venv venv
source ./venv/bin/activate
pip3 install -r requirements.txt

printf "Setting up directory structure..."
./setup_directories.sh "$@"
python3 ./main.py "$@"
chmod +x ./DaVinci_Resolve_*_Linux.run

./setup_resolve.sh "$@"
install -Dm755 resolve.sh /app/bin/resolve.sh

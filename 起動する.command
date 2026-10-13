#!/bin/bash
# Mieie 見える図面 配布ツール ― 起動(ダブルクリック用)
cd "$(dirname "$0")"
echo "配布ツールを起動します。終了するときは Control + C"
echo
python3 mieie_haifu.py

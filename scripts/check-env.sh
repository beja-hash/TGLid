#!/bin/sh
set -eu

if [ ! -f .env ]; then
  echo "Файл .env не найден. Скопируйте .env.example в .env и при необходимости измените локальные значения." >&2
  exit 1
fi

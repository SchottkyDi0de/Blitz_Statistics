# Blitz Statistics BlitzHUB Project Page:
Support [![Discord](https://img.shields.io/badge/Discord-%235865F2.svg?&logo=discord&logoColor=white)](https://discord.gg/24FAU6Gbv2)
# License: MIT
Copyright 2024 vladislawzero@gmail.com | discord: _zener_diode | https://github.com/SchottkyDi0de

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), 
  to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, 
  and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
    The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, 
  EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, 
  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
  
IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, 
  DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, 
  ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

This license applies to all files in this project that contain Python source code unless otherwise specified!

# Command documentation
View docs in [![GitBook](https://img.shields.io/badge/GitBook-3884FF?logo=gitbook&logoColor=fff)](https://blitzhub.gitbook.io/blitz-statistics-bot)

# Used libriares:
py-cord 2.6.0

pyyaml 6.0.1

aiohttp 3.8.5

asynciolimiter 1.0.0

python-easy-json 1.1.9

python-dotenv 1.0.0

pillow 10.0.1

elara 0.5.5

cacheout 0.14.1

pydantic 2.4.2

the_retry 0.1.1

webcolors 1.13

fastapi 0.109.2

uvicorn 0.23.2

websockets 12.0

nicegui 1.4.24

typer 0.12.3

dynamic-yaml 2.0.0

motor 3.4.0

asgiref 3.8.1

numpy 2.0.0

filesplit 4.0.1


# Dependencies
[Python 3.11](https://www.python.org/downloads/release/python-3110/) or later

[datamodel-code-generator](https://github.com/koxudaxi/datamodel-code-generator/) for `dev_tools/locale_gen.py`

[MongoDB Server](https://www.mongodb.com/try/download/community)

[MongoDB Database Tools](https://www.mongodb.com/try/download/database-tools) (for dumper)

[WOTB Replay parser tool](https://github.com/eigenein/wotbreplay-parser) (project include compiled version for win 10 - 11 and linux)

# Supported platform:
Any linux distribution capable of installing all dependencies (our server was on ubuntu 22.04 LTS)

Windows 8 or later
# Deployment
## 1: Install all dependencies

## 2: Create virtual enviroment for python libs
```bash
python3 -m venv .env
```
**and activate**
### windows:
```cmd
.env/scripts/activate
```
### Linux
```bash
source .env/bin/activate
```
## 3: install all required libs
```bash
pip install -r requirements.txt
```
If there are some package conflicts during installation, remove the `nicegui` library from `requirements.txt` and try again, after installation write `pip install nicegui` separately

## 4: Setup
Go to `lib/settings/` and create file `.env`

The `.env` file should have the following content (instead of <> text you should specify your data)

```env
DISCORD_TOKEN=<your main token>
DISCORD_TOKEN_DEV=<your test token>

WG_APP_ID_CL0=<Wargaming API Key 1>
WG_APP_ID_CL1=<Wargaming API Key 2>

LT_APP_ID_CL0=<Lesta API Key 1>
LT_APP_ID_CL1=<Lesta API Key 2>

INTERNAL_API_KEY=<Key for acces to the internal API - Any string>

# OAuth
CLIENT_ID=<Discord client (app) ID>
CLIENT_SECRET=<Discord client secret>

CLIENT_ID_DEV=<Like CLIENT_ID but for test running>
CLIENT_SECRET_DEV=<Like CLIENT_SECRET but for test running>
```
create `logs` folder in root of project

## 5: Running
Run the bot in the order specified in `startup_info.md`

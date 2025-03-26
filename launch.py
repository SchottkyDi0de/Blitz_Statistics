import os
import sys

from typer import Typer
import yaml

from launch.launch_config import LaunchConfig, env_config

app = Typer()

@app.command()
def launch(mode: str):
    launch_config = LaunchConfig().get()
    
    if os.name == 'posix':
        os.system('chmod 777 lib/replay_parser/bin/parser')
    
    if mode == 'prod':
        print('Starting bot in production mode...')
        with open('settings/settings.yaml', 'r') as f:
            print('Updating settings.yaml...')
            config = yaml.safe_load(f)
            config['server']['host'] = launch_config.bot_launch_config.prod.host
            config['server']['port'] = launch_config.bot_launch_config.prod.port
            config['server']['protocol'] = launch_config.bot_launch_config.prod.protocol

        with open('settings/settings.yaml', 'w') as f:
            yaml.dump(config, f, indent=2, sort_keys=False)
        
        print('Done...')    
        os.system(f'python main.py {env_config.DISCORD_TOKEN}')
        
    elif mode == 'dev':
        print('Starting bot in development mode...')
        with open('settings/settings.yaml', 'r') as f:
            print('Updating settings.yaml...')
            config = yaml.safe_load(f)
            config['server']['host'] = launch_config.bot_launch_config.dev.host
            config['server']['port'] = launch_config.bot_launch_config.dev.port
            config['server']['protocol'] = launch_config.bot_launch_config.dev.protocol
        
        with open('settings/settings.yaml', 'w') as f:
            yaml.dump(config, f, indent=2, sort_keys=False)
        
        print('Done...')
        command = ' '.join((sys.executable, "main.py", env_config.DISCORD_TOKEN_DEV))
        os.system(command)
    else:
        raise ValueError('Invalid mode. Must be either "prod" or "dev"')

if __name__ == '__main__':
    app()

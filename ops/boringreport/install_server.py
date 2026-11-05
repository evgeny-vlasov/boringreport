import pathlib
import shutil

home = pathlib.Path.home()
repo = home / 'projects/boringreport-service'
bin_dir = home / '.local/lib/boringreport'
units = home / '.config/systemd/user'
config = home / '.config/boringreport'
for directory in [bin_dir, units, config]:
    directory.mkdir(parents=True, exist_ok=True)
config.chmod(0o700)
shutil.copyfile('/tmp/boringreport-server-runner.py', bin_dir / 'runner.py')
for action, hours in [('prepare','02,03'), ('deliver','04,05,06')]:
    name = f'boringreport-{action}'
    (units / f'{name}.service').write_text(f'''[Unit]
Description=Boring Report {action}
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory={repo}
Environment=PATH=/usr/local/bin:/usr/bin:/bin
ExecStart=/usr/bin/python3 {bin_dir}/runner.py {action}
TimeoutStartSec=2h
UMask=0077
''')
    (units / f'{name}.timer').write_text(f'''[Unit]
Description=Tuesday Boring Report {action} (Mountain Time)

[Timer]
OnCalendar=Tue *-*-* {hours}:00:00 America/Edmonton
Persistent=true
Unit={name}.service

[Install]
WantedBy=timers.target
''')
print('Installed runner and timers; timers intentionally disabled until Gmail authorization and end-to-end test succeed.')

from pathlib import Path

home = Path.home()
units = home / '.config/systemd/user'
for action in ['prepare', 'deliver']:
    dropin = units / f'boringreport-{action}.service.d'
    dropin.mkdir(parents=True, exist_ok=True)
    (dropin / 'failure.conf').write_text('[Unit]\nOnFailure=boringreport-failure@%n.service\n')
(units / 'boringreport-failure@.service').write_text(f'''[Unit]
Description=Boring Report failure notification for %i
After=network-online.target

[Service]
Type=oneshot
Environment=PATH=/usr/local/bin:/usr/bin:/bin
ExecStart=/usr/bin/python3 {home}/.local/lib/boringreport/runner.py notify-failure --unit %i
TimeoutStartSec=3min
UMask=0077
''')

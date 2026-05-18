import json
cfg = {
  "email": "",
  "save_password": False,
  "interval_min": 5,
  "start_minimized": False,
  "autostart": False
}
with open(r"C:\Users\under\.formadep_config.json","w",encoding="utf-8") as f:
    json.dump(cfg,f,indent=2)
print('written')

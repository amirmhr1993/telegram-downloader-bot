import os, site
sp = site.getsitepackages()[0]
d = os.path.join(sp, 'nodejs_wheel')
os.makedirs(d, exist_ok=True)
with open(os.path.join(d, '__init__.py'), 'w') as f:
    f.write('')
with open(os.path.join(d, 'executable.py'), 'w') as f:
    f.write('ROOT_DIR = r"C:\\Program Files\\nodejs"\n')
print('Done')

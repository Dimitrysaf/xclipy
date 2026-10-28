project(
  'xclipy',
  version: '0.1.0',
  meson_version: '>= 0.59.0',
)

prefix = get_option('prefix')
datadir = get_option('datadir')
bindir = get_option('bindir')

python = import('python').find_installation('python3')
python_module_dir = python.get_install_dir()
if prefix == '/usr'
  # Debian's system Python uses dist-packages instead of site-packages.
  python_module_dir = join_paths(prefix, 'lib/python3/dist-packages')
endif

install_subdir(
  'xclipy',
  install_dir: python_module_dir,
  exclude_directories: ['__pycache__', 'ui/__pycache__'],
)

# The "Clipboard" page in Cinnamon's System Settings.
install_data(
  'cinnamon-settings/cs_xclipy.py',
  install_dir: datadir / 'cinnamon' / 'cinnamon-settings' / 'modules',
)

launcher_conf = configuration_data()
launcher_conf.set('python_module_dir', python_module_dir)
launcher_conf.set('bindir', join_paths(prefix, bindir))

configure_file(
  input: 'data/xclipy.in',
  output: 'xclipy',
  configuration: launcher_conf,
  install: true,
  install_dir: bindir,
  install_mode: 'rwxr-xr-x',
)

configure_file(
  input: 'data/org.x.Xclipy.service.in',
  output: 'org.x.Xclipy.service',
  configuration: launcher_conf,
  install_dir: datadir / 'dbus-1' / 'services',
)
autostart_in = configure_file(
  input: 'data/org.x.Xclipy-autostart.desktop.in',
  output: 'org.x.Xclipy-autostart.desktop.in',
  configuration: launcher_conf,
)
import('i18n').merge_file(
  input: autostart_in,
  output: 'org.x.Xclipy-autostart.desktop',
  type: 'desktop',
  po_dir: meson.project_source_root() / 'po',
  install: true,
  install_dir: get_option('sysconfdir') / 'xdg' / 'autostart',
)

subdir('data')
subdir('po')

test_env = environment()
test_env.set('PYTHONPATH', meson.project_source_root())
test(
  'python-unit',
  python,
  args: ['-m', 'unittest', 'discover', '-s', meson.project_source_root() / 'tests'],
  env: test_env,
  workdir: meson.project_source_root(),
)

# -*- mode: python -*-

block_cipher = None

datas = [(r'atmcd64d.dll', '.'),
         (r'atmcd32d.dll', '.'),
         (r'./pyandor/gui/grayscale_bars.png', 'pyandor/gui')]

pathex = ['.',
          'C:\\Users\\Alex\\PycharmProjects\\pyandor',
          r'C:\Users\Alex\Anaconda3\envs\andor_dist\Library\lib']

a = Analysis(['pyandor\\gui\\pyandorGUI.py'],
             pathex=pathex,
             binaries=[],
             datas=datas,
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher)

pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)

exe = EXE(pyz,
          a.scripts,
          exclude_binaries=True,
          name='pyandorGUI',
          debug=False,
          strip=False,
          upx=True,
          console=False )

coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               name='pyandorGUI')

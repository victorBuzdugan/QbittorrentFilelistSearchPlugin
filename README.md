# qBitTorrent FileList search plugin
This a search plugin for qBitTorrent allowing in app search for filelist.io.

It's still in beta version requiring testing and feeback from users.

## Installing
Please follow this official guide:
https://github.com/qbittorrent/search-plugins/wiki/Install-search-plugins

## Post install - login
filelist.io is a private torrent site requiring login. You need to input your username and password in the filelist.py file or in an external .json file to enable searches.

- Method 1: input credentials in the .json file:
Download ```filelist_credentials_model.json``` from the repository, **rename** it to ```filelist_credentials.json```, edit it with your name and password and move it to the qBitTorrent ```engines``` folder (see bellow folder location).
```
qBittorrent
  nova3
    engines
      ...
      eztv.py
      filelist.py
      filelist_credentials.json
      filelist.log (see Logging bellow)
      jackett.py
      ...
```
- Method 2: input credentials in filelist.py
Open the ```filelist.py``` file and edit the values ```your_username_here``` and ```your_password_here```:
```python
credentials = {
    'username': 'your_username_here',
    'password': 'your_password_here'
}
```

### Priorities
If the scripts finds ```filelist_credentials.json``` in the same directory it will load credentials from the file and inhibit values from ```filelist.py```.

If you intend to input credentials directly in ```filelist.py``` don't use ```filelist_credentials.json```.

## Folder location
- Windows: ```%localappdata%\qBittorrent\nova3\engines\```
- Mac: ```~/Library/Application Support/qBittorrent/nova3/engines```

## Logging
After each search/download the script creates a filelist.log file that you can check if there are problems.

## To do list
- [ ] further testing

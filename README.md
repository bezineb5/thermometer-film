# Thermometer for film development
Use a Raspberry Pi to determine how long should the development of analog film should last.

## Features
* Web interface hosted on the Raspberry Pi
* Water temperature
* Air temperature
* High-precision sensors
* Development time based upon the film type and water temperature
* Scan the DX number directly from the website

## Important notes
The data provided corresponds to the 

## Hardware
You'll need:
* A Raspberry Pi (any version, the Zero W is perfect)
* A DS18B20 for water measure
* A Si7021 for air temperature

## Setup
Setup your Rasperry Pi with:
* Wifi/Network
* Enable 1-wire
* Enable I2C

This guide works on Debian Bookworm.

## Install the server

```bash
# Install pip for python 3
sudo apt install python3-pip -y

# Copy the thermometer-film folder to the Raspberry Pi
scp -r server pi@thermometre.local:~

# Install python libraries in a virtual environment
python3 -m venv ./venv
source ./venv/bin/activate
cd server
pip3 install -r requirements.txt

# Run the webapp as a service
sudo cp ./thermometer-webapp.service /etc/systemd/system

# Automatic start the service on boot
sudo systemctl enable thermometer-webapp.service

## Configure the firewall

```bash
# Forward port 80 to 5000 (where the webapp listens)
sudo apt install nftables -y
sudo systemctl enable nftables.service
sudo systemctl start nftables.service

# Create a new ruleset file
sudo tee /etc/nftables.conf << 'EOF'
#!/usr/sbin/nft -f

flush ruleset

table nat {
    chain prerouting {
        type nat hook prerouting priority -100; policy accept;
        tcp dport 80 redirect to :5000
    }
}
EOF

# Load the rules and make them persistent
sudo nft -f /etc/nftables.conf
```

## Configure Home Assistant
Store the configuration in the `config.json` file.

```bash
# Edit the config.json file
nano config.json
```

```json
{
  "home_assistant_mqtt_device": {
    "username": "mqtt_user",
    "password": "mqtt_password"
  }
}
```

## Restart the service

```bash
sudo systemctl restart thermometer-webapp.service
```

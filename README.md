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

```bash
# Install pip for python 3
sudo apt install python3-pip -y

# Copy the thermometer-film folder to the Raspberry Pi
scp -r thermometer-film pi@thermometre.local:~

# Install python libraries
cd thermometer-film
pip3 install -r requirements.txt

# Run the webapp as a service
sudo cp ./thermometer-webapp.service /etc/systemd/system

# Automatic start the service on boot
sudo systemctl enable thermometer-webapp.service

# Forward port 80 to 5000 (where the webapp listens)
sudo iptables -t nat -I PREROUTING -p tcp --dport 80 -j REDIRECT --to-ports 5000
sudo sh -c "mkdir -p /etc/iptables; iptables-save > /etc/iptables/rules.v4"
```

Then:
```bash
sudo vi /etc/rc.local
```
And add the following before the exit:
```bash
iptables-restore < /etc/iptables/rules.v4
```

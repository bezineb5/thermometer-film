import glob


def init_ds18b20():
    base_dir = '/sys/bus/w1/devices/'
    device_folder = glob.glob(base_dir + '28*')[0]
    device_file = device_folder + '/w1_slave'
 
    def read_temp():
        with open(device_file, 'r') as f:
            lines = f.readlines()
            status = lines[0].strip()[-3:]
            if status != 'YES':
                raise Exception("DS18B20 is not ready")
            equals_pos = lines[1].find('t=')
            if equals_pos != -1:
                temp_string = lines[1][equals_pos+2:]
                temp_c = float(temp_string) / 1000.0
                return temp_c
            else:
                raise Exception("DS18B20 did not provide temparture")
    
    return read_temp

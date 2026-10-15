# BlueZ required configuration

Edit:

```text
/etc/bluetooth/main.conf
```

Under `[General]`, make sure this line is active and **not commented**:

```ini
Experimental = true
```

Verify:

```bash
grep -nEi "Experimental" /etc/bluetooth/main.conf
```

Restart:

```bash
sudo systemctl restart bluetooth
sleep 3
sudo systemctl restart ars-ble
```

HCI validation:

```bash
sudo btmon -w ~/ars_interval_test.btsnoop
# send one answer, then Ctrl+C
sudo btmon -r ~/ars_interval_test.btsnoop | grep -A15 -B5 "LE Set Extended Adv"
```

Expected ACK advertising interval:

```text
Min advertising interval: 20.000 msec
Max advertising interval: 30.000 msec
```

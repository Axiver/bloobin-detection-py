# bloobin-detection-py
 
## Raspberry Pi Setup

### Touchscreen

#### Handling Custom Touchscreen Resolutions

1. `nano /boot/config.txt`

2. Add the following to the end of the file:
```
framebuffer_width=1024
framebuffer_height=600
hdmi_force_hotplug=1
hdmi_cvt=1024 600 60 3 0 0 0
hdmi_mode=87
```

3. Save the file and reboot and you should be running at the native 1024x600 resolution.

### Browser

To launch the built-in chromium browser in full-screen mode, run the following command:
`chromium-browser --start-fullscreen http://my_URL.com`

The URL should point to the frontned of the project.
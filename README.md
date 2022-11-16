# Hello Fairy Bluetooth Lights Integration for Home Assistant

This custom integration allows you to control Hello Fairy Bluetooth LED string lights from Home Assistant. The integration supports full RGB color control, brightness adjustment, and all built-in animated effects.

## Features

- **Full RGB Color Control**: Set any color using RGB values
- **Brightness Control**: Adjust brightness from 0-100%
- **Effect Support**: Access to 14 built-in animated effects including:
  - Blue White Dissolve
  - Blue Sparkle
  - White Sparkle
  - Blue with Pink Sparkle
  - Fireworks
  - Christmas themes (Xmas, Candy Cane)
  - Halloween
  - Holiday themes (Valentine, St. Patrick, July 4th, etc.)
- **Real-time Status**: Automatically syncs with device state changes (including remote control)
- **Bluetooth Low Energy**: Efficient BLE communication

## Supported Devices

This integration works with Hello Fairy Bluetooth LED string lights that advertise with the name pattern `Hello Fairy-*`. The protocol is based on the ESPHome configuration found in `fairy.yaml`.

### Protocol Details

- **Service UUID**: `49535343-fe7d-4ae5-8fa9-9fafd205e455`
- **Command UUID**: `49535343-8841-43f4-a8d4-ecbe34729bb3`
- **Notify UUID**: `49535343-1E4D-4BD9-BA61-23C647249616`

## Installation

1. Copy the `custom_components/hello_fairy_ble` folder to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant
3. Go to Settings > Devices & Services > Add Integration
4. Search for "Hello Fairy" and select it
5. Your Hello Fairy lights should be automatically discovered via Bluetooth

## Configuration

The integration uses Bluetooth discovery to automatically find Hello Fairy devices. No manual configuration is required if your device is within Bluetooth range.

### Manual Configuration

If automatic discovery doesn't work:

1. Go to Settings > Devices & Services > Add Integration
2. Search for "Hello Fairy Bluetooth Lights"
3. Select your device from the list of discovered devices
4. Complete the setup

## Usage

Once configured, your Hello Fairy lights will appear as a light entity in Home Assistant with the following capabilities:

- **On/Off Control**: Turn lights on and off
- **RGB Color**: Set custom colors using the color picker
- **Brightness**: Adjust brightness with the brightness slider
- **Effects**: Choose from 14 built-in effects in the effect dropdown

### Available Effects

The integration includes the following preset effects:

- Blue White Dissolve
- Blue Sparkle  
- White Sparkle
- Blue with Pink Sparkle
- Fireworks
- Xmas
- Candy Cane
- Halloween
- Red Gold
- July 4th
- Valentine
- St. Patrick
- May Day
- Snow Day

## Technical Implementation

The integration implements the Hello Fairy protocol as documented in the ESPHome configuration:

### Command Format

Commands use the following structure:
- `0xAA` (prefix) + command type + length + data + checksum

### Power Commands
- **On**: `AA 02 01 01 AE`
- **Off**: `AA 02 01 00 AD`

### Color Commands
- **HSV Color**: `AA 03 07 01 HHHH SSSS VVVV CC`
  - H: Hue (0-359 degrees, 2 bytes)
  - S: Saturation (0-1000, 2 bytes) 
  - V: Value/Brightness (0-1000, 2 bytes)
  - CC: Checksum

### Preset Commands  
- **Effect**: `AA 03 04 02 PP VVVV CC`
  - PP: Preset number (1-58)
  - VVVV: Brightness (0-1000, 2 bytes)
  - CC: Checksum

### Status Notifications

The device sends status updates via BLE notifications when state changes:
- Power state (byte 6): `00` = off, `01` = on  
- Mode (byte 7): `01` = color mode, `02` = preset mode
- Color data (bytes 8-13): HSV values when in color mode
- Preset data (bytes 8-10): Preset number and brightness when in preset mode

## Troubleshooting

### Device Not Discovered

1. Ensure the Hello Fairy lights are powered on and in pairing mode
2. Check that Bluetooth is enabled on your Home Assistant host
3. Verify the device name starts with "Hello Fairy-"
4. Try restarting the Bluetooth service or Home Assistant

### Connection Issues

1. Ensure the device is within Bluetooth range
2. Check for interference from other Bluetooth devices
3. Try power cycling the Hello Fairy lights
4. Restart the integration from Settings > Devices & Services

### Effect Not Working

1. Make sure the device is turned on before applying effects
2. Some effects may take a moment to activate
3. Try switching between color mode and effect mode

## Contributing

This integration is based on the protocol reverse-engineering work found in the `fairy.yaml` ESPHome configuration. Contributions and improvements are welcome!

## License

This project is provided as-is for personal use. Please respect the original device manufacturer's terms of service.
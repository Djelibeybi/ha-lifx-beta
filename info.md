# LIFX (Beta)

The LIFX Beta integration is a modified version of the core integration that allows manual configuration of certain discovery and retry values via the Home Assistant UI.

## Installation

Add <https://github.com/Djelibeybi/ha-lifx-beta> to [HACS](https://hacs.xyz) as
a custom repository and then install the Beta integration when it appears.

## Enable debug logging

The LIFX Beta integration will output a lot of (potentially useful) debug logs about its activities and discovery process. To see these logs, adjust your `logger` settings in `configuration.yaml` to enable `debug` for `custom_components.lifx`:

```yaml
logger:
  default: info
  logs:
    custom_components.lifx: debug
```

If you want to report an issue, please collect these logs first, then [open a GitHub issue](https://github.com/Djelibeybi/ha-lifx-beta/issues) and attach the logs. Be sure to review them first so you don't publish anything secret.

## Configuration Guide

The LIFX Beta integration _can only be configured via the UI_. Any configuration in `configuration.yaml` _will be ignored_. After installation, the beta will replace the built-in integration, so if you need to restore previous functionality, just uninstall the beta using HACS.

### Network selection and broadcasts

The LIFX Beta will not send discovery packets on multiple interfaces that are connected to the same network. It will instead use the first interface it finds on each network. To control this behaviour, ensure you enable only a single interface per network in Home Assistant.

### Configuration options

The following options are available by clicking the "Configure" button on the LIFX integration on the Devices and Services page in the Configuration section:

| Option                   | Default     | Description                                                                              |
| ------------------------ | ----------- | ---------------------------------------------------------------------------------------- |
| Discovery interval       | 60 seconds  | How long to wait between discovery scans of the network.                                 |
| Response timeout         | 1 second    | How long to wait for a reply from a bulb for each packet sent that requests a reply.     |
| Retry count              | 8 times     | How many retries before the integration starts the process of flagging the bulb offline. |
| Unavailable grace period | 180 seconds | How long in seconds must elapse without a response before a bulb is made unavailable.    |

### Calculating the minimum discovery interval value

The process of discovering bulbs generates a _lot_ of traffic, which can significantly impact wifi performance. To minimise the impact on your network, set the discovery interval to be at least _double_ the value of the number of bulbs on the network multiplied by the message response time multiplied by the retry count.

For example, using the default settings:

If there are **20** bulbs, each one gets **5** retries to respond within **1** second to the discovery packet broadcast, so discovery alone can take up to **100** seconds:

```plain
20 (bulbs) * 5 (retries) * 1 (response timeout)  = 100 (seconds)
```

To ensure the discovery process has finished before the next one starts, you should configure the discovery interval to at least **200** seconds or more.

#### Why double the time?

The calculation above only considers the initial broadcast packet and how many reply packets may hit the network. However, after each discovery reply is received, each bulb is sent and must reply to at least 4 more messages in order for Home Assistant to learn enough about the bulb to control it. Complex devices like Tiles, Candles, Beams and Z strips need 8-12 messages. Doubling the time interval is generally enough for this second wave of messages to complete and for the integration to hit a steady state.

## Further documentation

See the [LIFX documentation on the Home Assistant website](https://www.home-assistant.io/integrations/lifx).

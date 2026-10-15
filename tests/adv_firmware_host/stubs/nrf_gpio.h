#pragma once
#include <cstdint>
#include <vector>
#include <utility>
#define NRF_GPIO_PIN_MAP(p,n) ((p)*32+(n))
inline bool gpioHigh[64]={};
inline bool gpioOutput[64]={};
inline std::vector<std::pair<uint32_t,uint32_t>> fakeKeys;
inline void nrf_gpio_cfg_output(uint32_t p){gpioOutput[p]=true;}
inline void nrf_gpio_cfg_default(uint32_t p){gpioOutput[p]=false;}
inline void nrf_gpio_pin_set(uint32_t p){gpioHigh[p]=true;}
inline void nrf_gpio_pin_clear(uint32_t p){gpioHigh[p]=false;}
#define NRF_GPIO_PIN_NOPULL 0
#define NRF_GPIO_PIN_PULLUP 1
inline void nrf_gpio_cfg_input(uint32_t p,int pull){gpioOutput[p]=false;if(pull==NRF_GPIO_PIN_PULLUP)gpioHigh[p]=true;}
inline uint32_t nrf_gpio_pin_read(uint32_t p){
 for(auto key:fakeKeys) if(key.second==p && gpioOutput[key.first] && !gpioHigh[key.first])return 0;
 return gpioHigh[p]?1:0;
}

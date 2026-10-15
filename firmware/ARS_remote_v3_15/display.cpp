#include "display.h"
#include "board_pins.h"
#include <Arduino.h>
#include <nrf_gpio.h>
using namespace BoardPins;
static const uint32_t segPins[7] = {SEG_A,SEG_B,SEG_C,SEG_D,SEG_E,SEG_F,SEG_G};
static const uint8_t digits[10] = {0x3f,0x06,0x5b,0x4f,0x66,0x6d,0x7d,0x07,0x7f,0x6f};
// Answer codes stay 1..10 on the wire; only their visual representation changes.
// A, b, C, d, E, F, G, H, I, J. Lower-case b/d avoid looking like 8/0.
static const uint8_t answerGlyphs[10] = {0x77,0x7c,0x39,0x5e,0x79,0x71,0x3d,0x76,0x06,0x1e};
// bit 0..6 = A..G. Lower-case b/t/r/n/d are intentional on seven segments.
static constexpr uint8_t R=0x50,I=0x06,D=0x5e,N=0x54,A=0x77,B=0x7c,T=0x78,E=0x79,L=0x38,G=0x3d;
static uint8_t mode=DISP_NUMBER,value=0;
static uint32_t epoch=0,lastMuxUs=0;
static bool activeDigit=false;
static bool sleeping=false;
void displaySetSleeping(bool value) {
    sleeping=value;
    // Always disable both common anodes before changing segment outputs.
    nrf_gpio_pin_set(DIGIT_1);nrf_gpio_pin_set(DIGIT_2);
    for(uint8_t i=0;i<7;i++) nrf_gpio_pin_set(segPins[i]);
    if(!sleeping) {epoch=millis();lastMuxUs=micros()-2000u;}
}
void displaySetMode(uint8_t m,uint8_t v,bool valueFirst) {
    if(v>99) v=99;
    if(m!=mode || v!=value || valueFirst) {mode=m;value=v;epoch=millis()-(valueFirst?400u:0u);}
}
void displaySetNumber(uint8_t v) {displaySetMode(DISP_NUMBER,v);}
void displaySetDashes() {displaySetMode(DISP_WAIT);}
void displayBegin() {
    sleeping=false;
    for(uint8_t i=0;i<7;i++) {nrf_gpio_cfg_output(segPins[i]);nrf_gpio_pin_set(segPins[i]);}
    nrf_gpio_cfg_output(DIGIT_1);nrf_gpio_cfg_output(DIGIT_2);
    nrf_gpio_pin_set(DIGIT_1);nrf_gpio_pin_set(DIGIT_2);
    displaySetNumber(0);
}
void displayUpdate() {
    if(sleeping) return;
    uint32_t now=micros();
    if((uint32_t)(now-lastMuxUs)<2000) return;
    lastMuxUs=now;
    nrf_gpio_pin_set(DIGIT_1);nrf_gpio_pin_set(DIGIT_2);
    uint8_t a=digits[value/10],b=digits[value%10];
    uint32_t phase=(uint32_t)(millis()-epoch);
    bool label=phase%1200<400;
    switch(mode) {
        case DISP_ROOM: if(label){a=R;b=0;} break;
        case DISP_SEAT: if(label){a=I;b=D;} break;
        case DISP_QUESTION: if(label){a=N;b=0;} break;
        case DISP_ANSWER:
            a=0; // A single steady letter on the right digit, no numeric phase.
            b=(value>=1 && value<=10)?answerGlyphs[value-1]:0;
            break;
        case DISP_BLUETOOTH: a=(phase%800<500)?B:0;b=(phase%800<500)?T:0;break;
        case DISP_WAIT: a=(phase%500<250)?0x40:0;b=(phase%500<250)?0:0x40;break;
        case DISP_ERROR: a=E;b=R;break;
        case DISP_LOGIN: a=L;b=G;break;
        case DISP_CLOSED: a=0x39;b=L;break; // CL: current question closed
        case DISP_SYNC: a=0x40;b=0x40;break; // steady --: no usable current STATE
        default: break;
    }
    activeDigit=!activeDigit;
    uint8_t bits=activeDigit?b:a;
    for(uint8_t i=0;i<7;i++) {
        if(bits&(1u<<i)) nrf_gpio_pin_clear(segPins[i]);else nrf_gpio_pin_set(segPins[i]);
    }
    nrf_gpio_pin_clear(activeDigit?DIGIT_2:DIGIT_1);
}

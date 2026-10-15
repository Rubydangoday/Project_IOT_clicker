#pragma once
#include <stdint.h>
enum DisplayMode : uint8_t { DISP_NUMBER, DISP_ROOM, DISP_SEAT, DISP_QUESTION,
    DISP_ANSWER, DISP_BLUETOOTH, DISP_WAIT, DISP_ERROR, DISP_LOGIN,
    DISP_CLOSED, DISP_SYNC };
void displayBegin();
void displaySetNumber(uint8_t value);
void displaySetDashes();
void displaySetMode(uint8_t mode, uint8_t value = 0, bool valueFirst = false);
void displayUpdate();

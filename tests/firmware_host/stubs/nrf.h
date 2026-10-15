#pragma once
#include <cstdint>
struct FicrMock {uint32_t DEVICEID[2]={1,2};};
inline FicrMock fakeFicr;
#define NRF_FICR (&fakeFicr)

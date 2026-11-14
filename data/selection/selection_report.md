# Variable selection report

Candidates: 149 (left out: 29). Final set: **20** variables (6 headline + 14 data-driven) explaining **65.1%** of the pool's trend structure (headlines alone: 26.4%).

## Final set

| # | variable | role | family | +explained | drop-one loss | re-found | global trend/decade | divergence |
|---|---|---|---|---|---|---|---|---|
| 1 | M2TMNXSLV.T2M | headline | Temperature | - | 1.2% | - | +0.224 K | 0.04 |
| 2 | REYNOLDS_NCDC_L4_MONTHLY_V5.sst | headline | Ocean & sea ice | - | 0.5% | - | +0.223 degree_C | 0.00 |
| 3 | NASA_SSH_REF_SIMPLE_GRID_V11.ssha | headline | Ocean & sea ice | - | 0.5% | - | +0.0357 m | 0.01 |
| 4 | GPM_3IMERGM.precipitation | headline | Precipitation | - | 0.8% | - | +0.000936 mm/hr | 0.97 |
| 5 | MOD10CM.Snow_Cover_Monthly_CMG | headline | Snow | - | 0.7% | - | -0.207 none | 0.83 |
| 6 | MOD13C2.CMG 0.05 Deg Monthly NDVI | headline | Vegetation | - | 1.4% | - | +0.00801 NDVI | 0.10 |
| 7 | GLDAS_CLSM10_M.TWS_inst | data-driven | Soil moisture | 6.2% | 1.9% | 100% | -29.4 mm | 0.24 |
| 8 | M2TMNXRAD.SWGDN | data-driven | Radiation | 4.8% | 3.5% | 85% | -0.899 W m-2 | 0.39 |
| 9 | M2TMNXLND.GWETTOP | data-driven | Soil moisture | 4.0% | 2.5% | 100% | +0.00172 1 | 0.64 |
| 10 | GLDAS_VIC10_M.Swnet_tavg | data-driven | Land water & energy fluxes | 3.5% | 2.5% | 85% | +1.9 W m-2 | 0.26 |
| 11 | M2TMNXAER.TOTEXTTAU | data-driven | Aerosol optical depth | 3.0% | 2.5% | 95% | -0.000971 1 | 0.83 |
| 12 | GLDAS_NOAH025_M.SoilMoi10_40cm_inst | data-driven | Soil moisture | 2.5% | 2.1% | 75% | -0.687 kg m-2 | 0.71 |
| 13 | M2TMNXSLV.H500 | data-driven | Pressure & circulation | 2.4% | 1.7% | 75% | +7.15 m | 0.00 |
| 14 | GLDAS_CLSM10_M.Qle_tavg | data-driven | Land water & energy fluxes | 2.3% | 2.0% | 95% | +0.383 W m-2 | 0.88 |
| 15 | M2TMNXSLV.CLDTMP | data-driven | Humidity & clouds | 2.2% | 2.1% | 40% | -0.197 K | 0.54 |
| 16 | GLDAS_VIC10_M.Qs_acc | data-driven | Runoff | 1.8% | 1.5% | 45% | -0.00401 kg m-2 | 0.45 |
| 17 | FLDAS_NOAH01_C_GL_M.Evap_tavg | data-driven | Land water & energy fluxes | 1.7% | 1.7% | 70% | +8.57e-08 kg m-2 s-1 | 0.57 |
| 18 | GLDAS_NOAH025_M.SoilTMP0_10cm_inst | data-driven | Land temperature | 1.5% | 1.5% | 55% | +0.104 K | 0.90 |
| 19 | GLDAS_VIC10_M.SoilMoi_depth2_inst | data-driven | Soil moisture | 1.5% | 1.5% | 40% | -4.86 kg m-2 | 0.41 |
| 20 | M2TMNXFLX.EVAP | data-driven | Surface fluxes | 1.4% | 1.4% | 30% | -4.91e-07 kg m-2 s-1 | 0.64 |

## Loss if a whole family is removed

- Soil moisture: 8.8%
- Land water & energy fluxes: 6.3%
- Radiation: 3.5%
- Aerosol optical depth: 2.5%
- Humidity & clouds: 2.1%
- Pressure & circulation: 1.7%
- Runoff: 1.5%
- Land temperature: 1.5%
- Surface fluxes: 1.4%
- Vegetation: 1.4%
- Ocean & sea ice: 1.3%
- Temperature: 1.2%
- Precipitation: 0.8%
- Snow: 0.7%

## Redundancy (near-duplicates of each shown variable, |r| >= 0.90)

- **M2TMNXSLV.T2M**: M2SMNXSLV.T2MMAX, M2SMNXSLV.T2MMIN, M2TMNXSLV.TS, M2TMNXSLV.T850
- **REYNOLDS_NCDC_L4_MONTHLY_V5.sst**: M2TMNXOCN.TSKINWTR
- **NASA_SSH_REF_SIMPLE_GRID_V11.ssha**: none
- **GPM_3IMERGM.precipitation**: none
- **MOD10CM.Snow_Cover_Monthly_CMG**: none
- **MOD13C2.CMG 0.05 Deg Monthly NDVI**: MOD13C2.CMG 0.05 Deg Monthly EVI
- **GLDAS_CLSM10_M.TWS_inst**: GLDAS_CLSM10_M.SoilMoist_P_inst, GLDAS_CLSM10_M.SoilMoist_RZ_inst, GLDAS_CLSM10_M.SoilMoist_S_inst
- **M2TMNXRAD.SWGDN**: M2TMNXRAD.SWGNT, M2TMNXRAD.SWTNT
- **M2TMNXLND.GWETTOP**: M2TMNXLND.GWETROOT, M2TMNXLND.GWETPROF, M2TMNXLND.TWLAND
- **GLDAS_VIC10_M.Swnet_tavg**: GLDAS_CLSM10_M.Swnet_tavg
- **M2TMNXAER.TOTEXTTAU**: none
- **GLDAS_NOAH025_M.SoilMoi10_40cm_inst**: none
- **M2TMNXSLV.H500**: M2TMNXSLV.T250, M2TMNXSLV.T500
- **GLDAS_CLSM10_M.Qle_tavg**: GLDAS_CLSM10_M.Evap_tavg
- **M2TMNXSLV.CLDTMP**: none
- **GLDAS_VIC10_M.Qs_acc**: none
- **FLDAS_NOAH01_C_GL_M.Evap_tavg**: FLDAS_NOAH01_C_GL_M.Qle_tavg
- **GLDAS_NOAH025_M.SoilTMP0_10cm_inst**: GLDAS_NOAH025_M.AvgSurfT_inst
- **GLDAS_VIC10_M.SoilMoi_depth2_inst**: none
- **M2TMNXFLX.EVAP**: M2TMNXFLX.EFLUX

## Strongest regional divergence among candidates (opposing significant trends)

- M2TMNXAER.SSCMASS: divergence 0.98
- GPM_3IMERGM.precipitation: divergence 0.97 (headline)
- M2TMNXRAD.LWTUP: divergence 0.96
- M2TMNXRAD.LWTUPCLR: divergence 0.95
- GLDAS_CLSM10_M.Qh_tavg: divergence 0.94
- GLDAS_NOAH025_M.AvgSurfT_inst: divergence 0.93
- FLDAS_NOAH01_C_GL_M.Swnet_tavg: divergence 0.92
- FLDAS_NOAH01_C_GL_M.SoilMoi40_100cm_tavg: divergence 0.92
- M2TMNXFLX.PRECTOTCORR: divergence 0.91
- GLDAS_NOAH025_M.SoilTMP0_10cm_inst: divergence 0.90 (data-driven)

## Left out

- FLDAS_NOAH01_C_GL_M.SWE_inst: valid cells 27% < 30%
- FLDAS_NOAH01_C_GL_M.SnowCover_inst: valid cells 26% < 30%
- FLDAS_NOAH01_C_GL_M.SnowDepth_inst: valid cells 27% < 30%
- FLDAS_NOAH01_C_GL_M.Snowf_tavg: valid cells 26% < 30%
- GLDAS_CLSM10_M.Qsb_acc: valid cells 19% < 30%
- GLDAS_CLSM10_M.Qsm_acc: valid cells 23% < 30%
- GLDAS_CLSM10_M.SWE_inst: valid cells 23% < 30%
- GLDAS_CLSM10_M.SnowDepth_inst: valid cells 23% < 30%
- GLDAS_CLSM10_M.Snowf_tavg: valid cells 23% < 30%
- GLDAS_NOAH025_M.Qsm_acc: valid cells 27% < 30%
- GLDAS_NOAH025_M.SWE_inst: valid cells 29% < 30%
- GLDAS_NOAH025_M.SnowDepth_inst: valid cells 29% < 30%
- GLDAS_NOAH025_M.Snowf_tavg: valid cells 27% < 30%
- GLDAS_VIC10_M.Albedo_inst: valid cells 24% < 30%
- GLDAS_VIC10_M.Qsm_acc: valid cells 24% < 30%
- GLDAS_VIC10_M.SWE_inst: valid cells 24% < 30%
- GLDAS_VIC10_M.SnowDepth_inst: valid cells 24% < 30%
- GLDAS_VIC10_M.Snowf_tavg: valid cells 24% < 30%
- M2TMNXADG.DUAERIDX: empty or constant in the source data
- M2TMNXADG.SSAERIDX: empty or constant in the source data
- M2TMNXGLC.SNICEALB: valid cells 4% < 30%
- M2TMNXGLC.SNOMAS_GL: valid cells 21% < 30%
- M2TMNXGLC.SNOWDP_GL: valid cells 21% < 30%
- M2TMNXLND.FRSNO: valid cells 29% < 30%
- M2TMNXLND.GRN: empty or constant in the source data
- M2TMNXLND.LAI: empty or constant in the source data
- M2TMNXLND.SNODP: valid cells 29% < 30%
- M2TMNXLND.SNOMAS: valid cells 29% < 30%
- MICASA_FLUX_M.FIRE: valid cells 28% < 30%

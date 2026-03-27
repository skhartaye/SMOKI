/**
 * AQI Calculator for Philippine Air Quality Standards
 * Adapted for MICS-6814 sensor (relative measurements)
 * Based on DENR Administrative Order No. 2021-07
 * 
 * IMPORTANT: MICS-6814 sensors (NO₂, CO) provide relative measurements, not absolute PPM.
 * The sensor outputs voltage readings that are multiplied by 100 in the ESP32 code.
 * These ranges are calibrated based on typical MICS-6814 behavior and should be
 * adjusted based on your specific environment and sensor calibration.
 */

// MICS-6814 sensor ranges (relative values, not absolute PPM)
// These are calibrated ranges based on typical MICS-6814 output
const MICS6814_RANGES = {
  // NO₂ sensor output ranges (voltage * 100)
  no2: [
    { low: 0, high: 5, aqiLow: 0, aqiHigh: 25 },        // Good
    { low: 5.1, high: 10, aqiLow: 25.1, aqiHigh: 35 },  // Fair
    { low: 10.1, high: 15, aqiLow: 35.1, aqiHigh: 45 }, // Unhealthy for Sensitive
    { low: 15.1, high: 20, aqiLow: 45.1, aqiHigh: 55 }, // Very Unhealthy
    { low: 20.1, high: 30, aqiLow: 55.1, aqiHigh: 90 }, // Acutely Unhealthy
    { low: 30.1, high: 100, aqiLow: 91, aqiHigh: 500 }  // Emergency
  ],
  
  // CO sensor output ranges (voltage * 100)
  co: [
    { low: 0, high: 3, aqiLow: 0, aqiHigh: 25 },        // Good
    { low: 3.1, high: 6, aqiLow: 25.1, aqiHigh: 35 },   // Fair
    { low: 6.1, high: 10, aqiLow: 35.1, aqiHigh: 45 },  // Unhealthy for Sensitive
    { low: 10.1, high: 15, aqiLow: 45.1, aqiHigh: 55 }, // Very Unhealthy
    { low: 15.1, high: 25, aqiLow: 55.1, aqiHigh: 90 }, // Acutely Unhealthy
    { low: 25.1, high: 100, aqiLow: 91, aqiHigh: 500 }  // Emergency
  ]
};

// Standard AQI Breakpoints for PM sensors (these are accurate)
const AQI_BREAKPOINTS = {
  // PM2.5 (µg/Nm³) - 24 hour average - Philippine DENR Standards
  pm25: [
    { low: 0, high: 25, aqiLow: 0, aqiHigh: 25 },        // Good
    { low: 25.1, high: 35, aqiLow: 25.1, aqiHigh: 35 },  // Fair
    { low: 35.1, high: 45, aqiLow: 35.1, aqiHigh: 45 },  // Unhealthy for Sensitive
    { low: 45.1, high: 55, aqiLow: 45.1, aqiHigh: 55 },  // Very Unhealthy
    { low: 55.1, high: 90, aqiLow: 55.1, aqiHigh: 90 },  // Acutely Unhealthy
    { low: 91, high: 500, aqiLow: 91, aqiHigh: 500 }     // Emergency
  ],
  
  // PM10 (µg/Nm³) - 24 hour average - Philippine DENR Standards
  pm10: [
    { low: 0, high: 54, aqiLow: 0, aqiHigh: 25 },        // Good
    { low: 55, high: 154, aqiLow: 25.1, aqiHigh: 35 },   // Fair
    { low: 155, high: 254, aqiLow: 35.1, aqiHigh: 45 },  // Unhealthy for Sensitive
    { low: 255, high: 354, aqiLow: 45.1, aqiHigh: 55 },  // Very Unhealthy
    { low: 355, high: 424, aqiLow: 55.1, aqiHigh: 90 },  // Acutely Unhealthy
    { low: 425, high: 504, aqiLow: 91, aqiHigh: 500 }    // Emergency
  ]
};

/**
 * Calculate AQI for a single pollutant
 * @param {number} concentration - Pollutant concentration
 * @param {string} pollutant - Pollutant type (pm25, pm10, no2, co)
 * @returns {number} AQI value
 */
export function calculatePollutantAQI(concentration, pollutant) {
  if (concentration < 0) {
    return 0;
  }
  
  // Use MICS-6814 ranges for gas sensors, standard ranges for PM sensors
  let breakpoints;
  if (pollutant === 'no2' || pollutant === 'co') {
    breakpoints = MICS6814_RANGES[pollutant];
  } else {
    breakpoints = AQI_BREAKPOINTS[pollutant];
  }
  
  if (!breakpoints) {
    return 0;
  }
  
  // Find the appropriate breakpoint
  for (const bp of breakpoints) {
    if (concentration >= bp.low && concentration <= bp.high) {
      // Linear interpolation formula: AQI = ((AQI_hi - AQI_lo) / (C_hi - C_lo)) * (C - C_lo) + AQI_lo
      const aqi = ((bp.aqiHigh - bp.aqiLow) / (bp.high - bp.low)) * (concentration - bp.low) + bp.aqiLow;
      return Math.round(aqi);
    }
  }
  
  // If concentration exceeds all breakpoints, return maximum AQI
  return 500;
}

/**
 * Calculate overall AQI from multiple pollutants
 * @param {Object} pollutants - Object containing pollutant concentrations
 * @param {number} pollutants.no2 - NO₂ concentration in PPM
 * @param {number} pollutants.co - CO concentration in PPM
 * @param {number} pollutants.pm25 - PM2.5 concentration in µg/m³
 * @param {number} pollutants.pm10 - PM10 concentration in µg/m³
 * @returns {Object} AQI result with overall AQI and individual pollutant AQIs
 */
export function calculateOverallAQI(pollutants) {
  const individualAQIs = {};
  let maxAQI = 0;
  let dominantPollutant = null;
  
  // Calculate AQI for each pollutant
  Object.entries(pollutants).forEach(([pollutant, concentration]) => {
    if (concentration !== null && concentration !== undefined && concentration >= 0) {
      const aqi = calculatePollutantAQI(concentration, pollutant);
      individualAQIs[pollutant] = aqi;
      
      if (aqi > maxAQI) {
        maxAQI = aqi;
        dominantPollutant = pollutant;
      }
    }
  });
  
  return {
    overallAQI: maxAQI,
    dominantPollutant,
    individualAQIs,
    category: getAQICategory(maxAQI),
    healthMessage: getHealthMessage(maxAQI)
  };
}

/**
 * Get AQI category based on AQI value (Standard EPA System)
 * @param {number} aqi - AQI value
 * @returns {Object} Category information
 */
export function getAQICategory(aqi) {
  if (aqi <= 50) {
    return {
      level: 'Good',
      color: '#4CAF50',  // Green from image
      textColor: '#ffffff',
      description: 'Air quality is satisfactory'
    };
  } else if (aqi <= 100) {
    return {
      level: 'Moderate',
      color: '#FFC107',  // Yellow/Orange from image
      textColor: '#000000',
      description: 'Acceptable for most people'
    };
  } else if (aqi <= 150) {
    return {
      level: 'Unhealthy for Sensitive',
      color: '#FF9800',  // Orange from image
      textColor: '#ffffff',
      description: 'May affect sensitive groups'
    };
  } else if (aqi <= 200) {
    return {
      level: 'Unhealthy',
      color: '#F44336',  // Red from image
      textColor: '#ffffff',
      description: 'Everyone may experience effects'
    };
  } else if (aqi <= 300) {
    return {
      level: 'Very Unhealthy',
      color: '#9C27B0',  // Purple from image
      textColor: '#ffffff',
      description: 'Health alert for everyone'
    };
  } else {
    return {
      level: 'Hazardous',
      color: '#673AB7',  // Dark Purple from image
      textColor: '#ffffff',
      description: 'Emergency conditions'
    };
  }
}

/**
 * Get health message based on AQI value (Standard EPA System)
 * @param {number} aqi - AQI value
 * @returns {string} Health message
 */
export function getHealthMessage(aqi) {
  if (aqi <= 50) {
    return 'Air quality is satisfactory';
  } else if (aqi <= 100) {
    return 'Acceptable for most people';
  } else if (aqi <= 150) {
    return 'May affect sensitive groups';
  } else if (aqi <= 200) {
    return 'Everyone may experience effects';
  } else if (aqi <= 300) {
    return 'Health alert for everyone';
  } else {
    return 'Emergency conditions';
  }
}

/**
 * Get pollutant display name
 * @param {string} pollutant - Pollutant code
 * @returns {string} Display name
 */
export function getPollutantDisplayName(pollutant) {
  const names = {
    pm25: 'PM2.5',
    pm10: 'PM10',
    no2: 'NO₂',
    co: 'CO'
  };
  return names[pollutant] || pollutant.toUpperCase();
}

/**
 * Get pollutant unit
 * @param {string} pollutant - Pollutant code
 * @returns {string} Unit
 */
export function getPollutantUnit(pollutant) {
  const units = {
    pm25: 'µg/m³',
    pm10: 'µg/m³',
    no2: 'sensor value', // MICS-6814 relative measurement
    co: 'sensor value'   // MICS-6814 relative measurement
  };
  return units[pollutant] || '';
}
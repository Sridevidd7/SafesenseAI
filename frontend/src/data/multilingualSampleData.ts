/**
 * SafeSense AI — Multilingual Sample Dataset
 *
 * 30 synthetic safety reports in English, Kannada, and Hindi.
 * Covers: Confined Space, Energy Isolation, Hot Work, Line of Fire,
 *         PPE, Housekeeping, Working at Height, Vehicle Movement.
 *
 * USE: Synthetic demo/test data only.
 * Do NOT represent this as real OIL organizational data.
 */

export interface MultilingualSampleRow {
  report_id: string;
  report_type: string;
  report_text: string;           // Original language text
  language: string;              // 'en' | 'kn' | 'hi'
  activity: string;
  location: string;
  site: string;
  severity: string;
  sif_potential: string;
  life_saving_rule: string;
  barrier_failure: string;
  recommended_action: string;
  date: string;
  // Expected after translation (for test verification)
  expected_english_keywords?: string[];
}

export const MULTILINGUAL_SAMPLE_REPORTS: MultilingualSampleRow[] = [
  // ─── ENGLISH (15 reports) ───────────────────────────────────────────────
  {
    report_id: 'ML-001', report_type: 'Unsafe Act', language: 'en',
    report_text: 'Worker entered a confined space without completing required gas testing and permit verification.',
    activity: 'Confined Space Entry', location: 'Unit 3', site: 'Site Alpha',
    severity: 'Critical', sif_potential: 'YES', life_saving_rule: 'Confined Space',
    barrier_failure: 'Gas Testing Not Completed',
    recommended_action: 'Stop entry. Complete gas testing. Obtain permit. Assign standby person.',
    date: '2025-11-10',
    expected_english_keywords: ['confined space', 'without', 'gas testing'],
  },
  {
    report_id: 'ML-002', report_type: 'Unsafe Act', language: 'en',
    report_text: 'Maintenance technician began electrical work on a live control panel without applying lockout/tagout.',
    activity: 'Maintenance - Electrical', location: 'Substation B', site: 'Site Beta',
    severity: 'Critical', sif_potential: 'YES', life_saving_rule: 'Energy Isolation',
    barrier_failure: 'Isolation Not Applied',
    recommended_action: 'Stop work. Apply LOTO. Verify zero energy. Issue isolation certificate.',
    date: '2025-11-12',
    expected_english_keywords: ['electrical work', 'lockout', 'live'],
  },
  {
    report_id: 'ML-003', report_type: 'Unsafe Condition', language: 'en',
    report_text: 'Welding observed in hazardous area without a valid hot work permit. Flammable vapors detected nearby.',
    activity: 'Hot Work', location: 'Tank Farm', site: 'Site Alpha',
    severity: 'Critical', sif_potential: 'YES', life_saving_rule: 'Hot Work',
    barrier_failure: 'Hot Work Permit Not Obtained',
    recommended_action: 'Stop welding. Obtain permit. Conduct gas test. Post fire watch.',
    date: '2025-11-14',
    expected_english_keywords: ['welding', 'without', 'hot work permit'],
  },
  {
    report_id: 'ML-004', report_type: 'Near Miss', language: 'en',
    report_text: 'Worker walked under a suspended crane load. No exclusion zone was established around the lift area.',
    activity: 'Lifting Operations', location: 'Loading Bay', site: 'Site Gamma',
    severity: 'High', sif_potential: 'YES', life_saving_rule: 'Line of Fire',
    barrier_failure: 'Exclusion Zone Not Established',
    recommended_action: 'Establish exclusion zone. Review lift plan. Brief all workers.',
    date: '2025-11-15',
    expected_english_keywords: ['suspended', 'exclusion zone', 'crane'],
  },
  {
    report_id: 'ML-005', report_type: 'Unsafe Act', language: 'en',
    report_text: 'Worker observed at 5-meter height without safety harness or fall-arrest equipment.',
    activity: 'Working at Height', location: 'Reactor Area', site: 'Site Beta',
    severity: 'High', sif_potential: 'YES', life_saving_rule: 'Working at Height',
    barrier_failure: 'Fall Protection Not Used',
    recommended_action: 'Stop work. Fit harness. Install guardrails. Inspect scaffold.',
    date: '2025-11-16',
    expected_english_keywords: ['height', 'without harness', 'fall'],
  },
  {
    report_id: 'ML-006', report_type: 'Unsafe Condition', language: 'en',
    report_text: 'Worker handling sulfuric acid without chemical-resistant gloves or face shield. PPE station was empty.',
    activity: 'Chemical Handling', location: 'Pump House', site: 'Site Delta',
    severity: 'High', sif_potential: 'YES', life_saving_rule: 'Chemical Handling',
    barrier_failure: 'PPE Not Available',
    recommended_action: 'Stop chemical work. Restock PPE. Conduct hazard briefing.',
    date: '2025-11-17',
    expected_english_keywords: ['without', 'ppe', 'acid'],
  },
  {
    report_id: 'ML-007', report_type: 'Near Miss', language: 'en',
    report_text: 'Forklift reversed toward workers in pedestrian walkway. Reversing alarms were not functioning.',
    activity: 'Vehicle Movement', location: 'Workshop 2', site: 'Site Alpha',
    severity: 'High', sif_potential: 'YES', life_saving_rule: 'Vehicle Movement',
    barrier_failure: 'Pedestrian Segregation Not Maintained',
    recommended_action: 'Re-establish segregation. Repair reversing alarms. Assign banksman.',
    date: '2025-11-18',
    expected_english_keywords: ['forklift', 'pedestrian', 'reversing'],
  },
  {
    report_id: 'ML-008', report_type: 'Unsafe Condition', language: 'en',
    report_text: 'Trailing cables across workshop walkway creating trip hazard. No cable management in place.',
    activity: 'General Inspection', location: 'Workshop 2', site: 'Site Gamma',
    severity: 'Low', sif_potential: 'NO', life_saving_rule: 'General Safety',
    barrier_failure: 'Housekeeping Standards Not Met',
    recommended_action: 'Remove cables. Install cable management. Conduct inspection.',
    date: '2025-11-19',
    expected_english_keywords: ['cables', 'trip', 'walkway'],
  },
  {
    report_id: 'ML-009', report_type: 'Incident', language: 'en',
    report_text: 'Worker incapacitated inside confined space due to oxygen-deficient atmosphere. Rescue team was not on standby.',
    activity: 'Confined Space Entry', location: 'Drain Area', site: 'Site Beta',
    severity: 'Critical', sif_potential: 'YES', life_saving_rule: 'Confined Space',
    barrier_failure: 'Rescue Plan Not Available',
    recommended_action: 'Stop all confined space work. Investigate. Review rescue procedure. Calibrate gas detectors.',
    date: '2025-11-20',
    expected_english_keywords: ['confined space', 'oxygen', 'rescue'],
  },
  {
    report_id: 'ML-010', report_type: 'Unsafe Act', language: 'en',
    report_text: 'Driver observed not wearing seat belt while operating company vehicle on site road.',
    activity: 'Driving / Vehicle', location: 'Site Road', site: 'Site Alpha',
    severity: 'Medium', sif_potential: 'NO', life_saving_rule: 'Vehicle Movement',
    barrier_failure: 'Seat Belt Not Worn',
    recommended_action: 'Reinforce seat-belt policy. Brief drivers. Conduct spot checks.',
    date: '2025-11-21',
    expected_english_keywords: ['seat belt', 'vehicle', 'driver'],
  },
  {
    report_id: 'ML-011', report_type: 'Unsafe Condition', language: 'en',
    report_text: 'Exposed live 415V conductors found in junction box. Cover was missing and area accessible.',
    activity: 'Electrical Work', location: 'Cable Trench', site: 'Site Delta',
    severity: 'Critical', sif_potential: 'YES', life_saving_rule: 'Energy Isolation',
    barrier_failure: 'Exposed Live Parts',
    recommended_action: 'De-energize conductors. Replace cover. Conduct electrical audit.',
    date: '2025-11-22',
    expected_english_keywords: ['live', 'conductor', 'exposed'],
  },
  {
    report_id: 'ML-012', report_type: 'Near Miss', language: 'en',
    report_text: 'Scaffold board broke under worker at 4m height. Worker fell but was caught by harness.',
    activity: 'Working at Height', location: 'Reactor Area', site: 'Site Beta',
    severity: 'High', sif_potential: 'YES', life_saving_rule: 'Working at Height',
    barrier_failure: 'Scaffold Not Inspected',
    recommended_action: 'Inspect all scaffolding. Replace damaged boards. Verify load ratings.',
    date: '2025-11-23',
    expected_english_keywords: ['scaffold', 'height', 'harness'],
  },
  {
    report_id: 'ML-013', report_type: 'Unsafe Act', language: 'en',
    report_text: 'Grinding work carried out near open hydrocarbon drain without hot work permit or fire watch.',
    activity: 'Hot Work', location: 'Process Area', site: 'Site Alpha',
    severity: 'Critical', sif_potential: 'YES', life_saving_rule: 'Hot Work',
    barrier_failure: 'Fire Watch Not Posted',
    recommended_action: 'Stop grinding. Obtain permit. Post fire watch. Remove ignition sources.',
    date: '2025-11-24',
    expected_english_keywords: ['grinding', 'without', 'fire watch'],
  },
  {
    report_id: 'ML-014', report_type: 'Unsafe Condition', language: 'en',
    report_text: 'Fire suppression system was manually isolated during maintenance and not reinstated afterward.',
    activity: 'Fire Safety', location: 'Control Room', site: 'Site Gamma',
    severity: 'Critical', sif_potential: 'YES', life_saving_rule: 'Fire Prevention',
    barrier_failure: 'Fire Detection Disabled',
    recommended_action: 'Reinstate fire suppression. Conduct system audit. Report all defects immediately.',
    date: '2025-11-25',
    expected_english_keywords: ['fire suppression', 'isolated', 'maintenance'],
  },
  {
    report_id: 'ML-015', report_type: 'Near Miss', language: 'en',
    report_text: 'Pressurized pipework was opened during mechanical maintenance without releasing stored pressure first.',
    activity: 'Maintenance - Mechanical', location: 'Compressor House', site: 'Site Delta',
    severity: 'Critical', sif_potential: 'YES', life_saving_rule: 'Energy Isolation',
    barrier_failure: 'Pressure Not Released',
    recommended_action: 'Stop maintenance. Verify zero pressure. Issue energy isolation certificate.',
    date: '2025-11-26',
    expected_english_keywords: ['pressurized', 'without', 'pressure'],
  },

  // ─── KANNADA (8 reports) ────────────────────────────────────────────────
  {
    report_id: 'ML-016', report_type: 'Unsafe Act', language: 'kn',
    report_text: 'ಕಾರ್ಮಿಕರು ಗ್ಯಾಸ್ ಪರೀಕ್ಷೆ ಮಾಡದೆ ಕನ್ಫೈನ್ಡ್ ಸ್ಪೇಸ್ ಒಳಗೆ ಪ್ರವೇಶಿಸಿದರು. ಅನುಮತಿ ಪಡೆಯದೆ ಕೆಲಸ ಮಾಡಿದರು.',
    activity: 'Confined Space Entry', location: 'Unit 3', site: 'Site Alpha',
    severity: 'Critical', sif_potential: 'YES', life_saving_rule: 'Confined Space',
    barrier_failure: 'Gas Testing Not Completed',
    recommended_action: 'Stop entry. Complete atmospheric gas testing. Obtain entry permit.',
    date: '2025-11-10',
    expected_english_keywords: ['confined space', 'gas testing', 'without permit'],
  },
  {
    report_id: 'ML-017', report_type: 'Unsafe Act', language: 'kn',
    report_text: 'ತಂತ್ರಜ್ಞ ಶಕ್ತಿ ಪ್ರತ್ಯೇಕತೆ ಮಾಡದೆ ವಿದ್ಯುತ್ ಕೆಲಸ ಮಾಡಿದರು. ಲಾಕ್ ಔಟ್ ಅನ್ವಯಿಸಲಿಲ್ಲ.',
    activity: 'Maintenance - Electrical', location: 'Substation B', site: 'Site Beta',
    severity: 'Critical', sif_potential: 'YES', life_saving_rule: 'Energy Isolation',
    barrier_failure: 'Isolation Not Applied',
    recommended_action: 'Stop work. Apply lockout. Verify zero energy state.',
    date: '2025-11-11',
    expected_english_keywords: ['energy isolation', 'electrical work', 'lockout'],
  },
  {
    report_id: 'ML-018', report_type: 'Unsafe Condition', language: 'kn',
    report_text: 'ಹಾಟ್ ವರ್ಕ್ ಪರ್ಮಿಟ್ ಇಲ್ಲದೆ ವೆಲ್ಡಿಂಗ್ ಕೆಲಸ ನಡೆಯಿತು. ಬೆಂಕಿ ಕಾವಲು ಇರಲಿಲ್ಲ.',
    activity: 'Hot Work', location: 'Tank Farm', site: 'Site Alpha',
    severity: 'Critical', sif_potential: 'YES', life_saving_rule: 'Hot Work',
    barrier_failure: 'Hot Work Permit Not Obtained',
    recommended_action: 'Stop welding. Obtain hot work permit. Post fire watch.',
    date: '2025-11-12',
    expected_english_keywords: ['hot work permit', 'welding', 'fire watch'],
  },
  {
    report_id: 'ML-019', report_type: 'Near Miss', language: 'kn',
    report_text: 'ಕ್ರೇನ್ ಕಾರ್ಯಾಚರಣೆ ಸಮಯದಲ್ಲಿ ಅಮಾನತು ಲೋಡ್ ಅಡಿಯಲ್ಲಿ ಕಾರ್ಮಿಕ ನಡೆದರು. ಹೊರಗಿನ ವಲಯ ಇರಲಿಲ್ಲ.',
    activity: 'Lifting Operations', location: 'Loading Bay', site: 'Site Gamma',
    severity: 'High', sif_potential: 'YES', life_saving_rule: 'Line of Fire',
    barrier_failure: 'Exclusion Zone Not Established',
    recommended_action: 'Establish exclusion zone. Review lift plan. Brief workers.',
    date: '2025-11-13',
    expected_english_keywords: ['crane', 'suspended load', 'exclusion zone'],
  },
  {
    report_id: 'ML-020', report_type: 'Unsafe Act', language: 'kn',
    report_text: 'ಕಾರ್ಮಿಕ ಎತ್ತರದಲ್ಲಿ ಕೆಲಸ ಮಾಡುವಾಗ ಹಾರ್ನೆಸ್ ಇಲ್ಲದೆ ಕೆಲಸ ಮಾಡಿದರು.',
    activity: 'Working at Height', location: 'Reactor Area', site: 'Site Beta',
    severity: 'High', sif_potential: 'YES', life_saving_rule: 'Working at Height',
    barrier_failure: 'Fall Protection Not Used',
    recommended_action: 'Stop work. Fit harness. Install edge protection.',
    date: '2025-11-14',
    expected_english_keywords: ['working at height', 'without harness'],
  },
  {
    report_id: 'ML-021', report_type: 'Unsafe Condition', language: 'kn',
    report_text: 'ಕಾರ್ಮಿಕ ರಾಸಾಯನಿಕ ನಿರ್ವಹಣೆ ಸಮಯದಲ್ಲಿ ಪಿಪಿಇ ಧರಿಸದೆ ಕೆಲಸ ಮಾಡಿದರು.',
    activity: 'Chemical Handling', location: 'Pump House', site: 'Site Delta',
    severity: 'High', sif_potential: 'YES', life_saving_rule: 'Chemical Handling',
    barrier_failure: 'PPE Not Available',
    recommended_action: 'Stop chemical work. Provide correct PPE. Conduct hazard briefing.',
    date: '2025-11-15',
    expected_english_keywords: ['chemical', 'without ppe'],
  },
  {
    report_id: 'ML-022', report_type: 'Near Miss', language: 'kn',
    report_text: 'ಫೋರ್ಕ್‌ಲಿಫ್ಟ್ ಪಾದಚಾರಿ ಪ್ರದೇಶದಲ್ಲಿ ಕಾರ್ಯನಿರ್ವಹಿಸಿತು. ಪಾದಚಾರಿ ಪ್ರತ್ಯೇಕತೆ ಇರಲಿಲ್ಲ.',
    activity: 'Vehicle Movement', location: 'Workshop', site: 'Site Alpha',
    severity: 'High', sif_potential: 'YES', life_saving_rule: 'Vehicle Movement',
    barrier_failure: 'Pedestrian Segregation Not Maintained',
    recommended_action: 'Re-establish segregation. Repair alarms. Assign banksman.',
    date: '2025-11-16',
    expected_english_keywords: ['forklift', 'pedestrian', 'pedestrian segregation'],
  },
  {
    report_id: 'ML-023', report_type: 'Unsafe Condition', language: 'kn',
    report_text: 'ಕಾರ್ಯಸ್ಥಳದಲ್ಲಿ ಸ್ಲಿಪ್ ಮತ್ತು ಟ್ರಿಪ್ ಅಪಾಯ. ಅಸುರಕ್ಷಿತ ಸ್ಥಿತಿ ವರದಿ.',
    activity: 'General Inspection', location: 'Workshop 2', site: 'Site Gamma',
    severity: 'Low', sif_potential: 'NO', life_saving_rule: 'General Safety',
    barrier_failure: 'Housekeeping Standards Not Met',
    recommended_action: 'Clean area. Install warning signs. Conduct housekeeping inspection.',
    date: '2025-11-17',
    expected_english_keywords: ['unsafe condition'],
  },

  // ─── HINDI (7 reports) ──────────────────────────────────────────────────
  {
    report_id: 'ML-024', report_type: 'Unsafe Act', language: 'hi',
    report_text: 'श्रमिक ने गैस परीक्षण किए बिना सीमित स्थान में प्रवेश किया। अनुमति के बिना काम किया।',
    activity: 'Confined Space Entry', location: 'Unit 3', site: 'Site Alpha',
    severity: 'Critical', sif_potential: 'YES', life_saving_rule: 'Confined Space',
    barrier_failure: 'Gas Testing Not Completed',
    recommended_action: 'Stop entry. Complete gas testing. Obtain permit. Assign standby person.',
    date: '2025-11-10',
    expected_english_keywords: ['confined space', 'without', 'gas testing'],
  },
  {
    report_id: 'ML-025', report_type: 'Unsafe Act', language: 'hi',
    report_text: 'श्रमिक ने एनर्जी आइसोलेशन किए बिना विद्युत लाइन पर काम किया। लॉकआउट नहीं लगाया।',
    activity: 'Maintenance - Electrical', location: 'Substation B', site: 'Site Beta',
    severity: 'Critical', sif_potential: 'YES', life_saving_rule: 'Energy Isolation',
    barrier_failure: 'Isolation Not Applied',
    recommended_action: 'Stop work. Apply LOTO. Verify zero energy. Issue certificate.',
    date: '2025-11-11',
    expected_english_keywords: ['energy isolation', 'electrical line', 'lockout'],
  },
  {
    report_id: 'ML-026', report_type: 'Unsafe Condition', language: 'hi',
    report_text: 'हॉट वर्क परमिट के बिना वेल्डिंग हो रही थी। ज्वलनशील गैस के पास काम हुआ।',
    activity: 'Hot Work', location: 'Tank Farm', site: 'Site Alpha',
    severity: 'Critical', sif_potential: 'YES', life_saving_rule: 'Hot Work',
    barrier_failure: 'Hot Work Permit Not Obtained',
    recommended_action: 'Stop welding. Obtain permit. Gas test. Post fire watch.',
    date: '2025-11-12',
    expected_english_keywords: ['hot work permit', 'welding', 'flammable gas'],
  },
  {
    report_id: 'ML-027', report_type: 'Near Miss', language: 'hi',
    report_text: 'क्रेन ऑपरेशन के दौरान श्रमिक निलंबित भार के नीचे खड़े थे। बहिष्करण क्षेत्र नहीं था।',
    activity: 'Lifting Operations', location: 'Loading Bay', site: 'Site Gamma',
    severity: 'High', sif_potential: 'YES', life_saving_rule: 'Line of Fire',
    barrier_failure: 'Exclusion Zone Not Established',
    recommended_action: 'Establish exclusion zone. Review lift plan. Brief all workers.',
    date: '2025-11-13',
    expected_english_keywords: ['crane', 'suspended load', 'exclusion zone'],
  },
  {
    report_id: 'ML-028', report_type: 'Unsafe Act', language: 'hi',
    report_text: 'कर्मचारी ऊंचाई पर काम कर रहे थे लेकिन हार्नेस के बिना। सुरक्षा उपकरण उपलब्ध नहीं था।',
    activity: 'Working at Height', location: 'Reactor Area', site: 'Site Beta',
    severity: 'High', sif_potential: 'YES', life_saving_rule: 'Working at Height',
    barrier_failure: 'Fall Protection Not Used',
    recommended_action: 'Stop work. Provide harness. Install guardrails and edge protection.',
    date: '2025-11-14',
    expected_english_keywords: ['height', 'without harness', 'safety equipment'],
  },
  {
    report_id: 'ML-029', report_type: 'Unsafe Condition', language: 'hi',
    report_text: 'रासायनिक पदार्थ के साथ काम करते समय श्रमिक ने पीपीई पहने बिना काम किया।',
    activity: 'Chemical Handling', location: 'Pump House', site: 'Site Delta',
    severity: 'High', sif_potential: 'YES', life_saving_rule: 'Chemical Handling',
    barrier_failure: 'PPE Not Available',
    recommended_action: 'Stop chemical work. Provide PPE. Conduct hazard briefing.',
    date: '2025-11-15',
    expected_english_keywords: ['chemical', 'without ppe'],
  },
  {
    report_id: 'ML-030', report_type: 'Near Miss', language: 'hi',
    report_text: 'फोर्कलिफ्ट पैदल यात्री क्षेत्र में चल रहा था। पैदल यात्री पृथक्करण नहीं था।',
    activity: 'Vehicle Movement', location: 'Workshop', site: 'Site Alpha',
    severity: 'High', sif_potential: 'YES', life_saving_rule: 'Vehicle Movement',
    barrier_failure: 'Pedestrian Segregation Not Maintained',
    recommended_action: 'Re-establish pedestrian segregation. Assign banksman.',
    date: '2025-11-16',
    expected_english_keywords: ['forklift', 'pedestrian', 'pedestrian segregation'],
  },
];

// ─── CSV export helper ────────────────────────────────────────────────────────
export function generateMultilingualCSV(): string {
  const headers = [
    'report_id', 'report_type', 'report_text', 'language', 'activity',
    'location', 'site', 'severity', 'sif_potential', 'life_saving_rule',
    'barrier_failure', 'recommended_action', 'date',
  ];
  const rows = MULTILINGUAL_SAMPLE_REPORTS.map(r =>
    headers.map(h => {
      const val = String((r as unknown as Record<string, unknown>)[h] ?? '');
      return `"${val.replace(/"/g, '""')}"`;
    }).join(',')
  );
  return [headers.join(','), ...rows].join('\n');
}

// ─── Column mapping for this dataset ─────────────────────────────────────────
export const MULTILINGUAL_COLUMN_MAPPING = {
  report_text:       'report_text',
  sif_label:         'sif_potential',
  severity:          'severity',
  report_type:       'report_type',
  location:          'location',
  activity:          'activity',
  site:              'site',
  date:              'date',
  barrier_failure:   'barrier_failure',
  recommended_action:'recommended_action',
  life_saving_rule:  'life_saving_rule',
  // language hint column
  language:          'language',
};

export const MULTILINGUAL_COLUMNS = Object.values(MULTILINGUAL_COLUMN_MAPPING);

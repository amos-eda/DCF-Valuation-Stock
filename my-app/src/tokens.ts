export const spacing = {
  1: '0.25rem',
  2: '0.5rem',
  3: '1rem',
  4: '1.5rem',
  5: '2rem',
};

export const radii = {
  DEFAULT: '1rem', // 2xl
};

export const shadows = {
  sm: '0 1px 2px 0 rgba(0,0,0,0.05)',
  md: '0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -2px rgba(0,0,0,0.1)',
  lg: '0 10px 15px -3px rgba(0,0,0,0.1), 0 4px 6px -4px rgba(0,0,0,0.1)',
};

export const semanticColors = {
  success: '#15803d',
  'success-foreground': '#ffffff',
  warn: '#b45309',
  'warn-foreground': '#ffffff',
  error: '#dc2626',
  'error-foreground': '#ffffff',
  neutral: '#4b5563',
  'neutral-foreground': '#ffffff',
};

export const tokens = {
  spacing,
  radii,
  shadows,
  colors: semanticColors,
};

export default tokens;

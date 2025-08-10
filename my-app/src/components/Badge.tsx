import React from 'react';
import type { Status } from '../types';

interface BadgeProps {
  text: string;
  type: Status | 'SOON';
}

const Badge: React.FC<BadgeProps> = ({ text, type }) => {
  const className = type === 'SOON' ? 'badge soon' : `badge status-${type.toLowerCase()}`;
  return <span className={className}>{text}</span>;
};

export default Badge;

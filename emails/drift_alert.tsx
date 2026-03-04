import React from 'react';
import {
  Body,
  Button,
  Container,
  Head,
  Hr,
  Html,
  Img,
  Link,
  Preview,
  Row,
  Section,
  Text,
  Font,
} from '@react-email/components';
import { Tailwind } from '@react-email/tailwind';

interface TimeEntry {
  id: string;
  entry_date: string;
  hours: number;
  description: string;
  logged_by?: string;
}

interface DriftAlertProps {
  partnerName: string;
  engagementName: string;
  clientName: string;
  matterName: string;
  driftSeverity: 'warning' | 'critical';
  budgetConsumedPercent: number;
  unscopedHours: number;
  unscopedAmount: number;
  budgetRemaining: number;
  timeEntries: TimeEntry[];
  engagementUrl: string;
  changeOrderUrl?: string;
}

/**
 * Drift Alert Email Template
 *
 * Alerts partners when scope drift crosses warning or critical thresholds.
 * Includes specific time entries that caused the drift.
 */
export const DriftAlertEmail: React.FC<DriftAlertProps> = ({
  partnerName,
  engagementName,
  clientName,
  matterName,
  driftSeverity,
  budgetConsumedPercent,
  unscopedHours,
  unscopedAmount,
  budgetRemaining,
  timeEntries,
  engagementUrl,
  changeOrderUrl,
}) => {
  const isWarning = driftSeverity === 'warning';
  const isCritical = driftSeverity === 'critical';
  const bgColor = isCritical ? '#fee2e2' : '#fef3c7';
  const borderColor = isCritical ? '#dc2626' : '#f59e0b';
  const badgeColor = isCritical ? '#dc2626' : '#f59e0b';

  return (
    <Html>
      <Head>
        <Font
          fontFamily="Helvetica"
          fallbackFontFamily="Arial"
          webFont={{
            url: 'https://fonts.googleapis.com/css?family=Roboto:400,500,700',
            format: 'woff2',
          }}
        />
        <title>Engagement Alert: Scope Drift Detected</title>
      </Head>
      <Preview>
        {isCritical ? '🚨' : '⚠️'} Scope drift detected on {engagementName} -
        {unscopedHours.toFixed(1)} unscoped hours
      </Preview>

      <Body style={{ backgroundColor: '#f9fafb' }}>
        <Container style={{ maxWidth: '600px', marginTop: '20px' }}>
          {/* Header Alert Banner */}
          <Section
            style={{
              backgroundColor: bgColor,
              borderLeft: `4px solid ${borderColor}`,
              padding: '16px',
              marginBottom: '24px',
              borderRadius: '4px',
            }}
          >
            <Row>
              <Text style={{ margin: '0 0 8px 0', fontSize: '14px', color: '#7c2d12' }}>
                <strong>
                  {isCritical ? '🚨 CRITICAL' : '⚠️ WARNING'}: Scope Drift Detected
                </strong>
              </Text>
            </Row>
            <Row>
              <Text style={{ margin: '0', fontSize: '13px', color: '#92400e' }}>
                {engagementName} • {clientName}
              </Text>
            </Row>
          </Section>

          {/* Main Content */}
          <Section style={{ backgroundColor: '#ffffff', padding: '32px', borderRadius: '8px' }}>
            <Text style={{ margin: '0 0 16px 0', fontSize: '16px', fontWeight: '600' }}>
              Hi {partnerName},
            </Text>

            <Text style={{ margin: '0 0 20px 0', fontSize: '14px', lineHeight: '1.6', color: '#374151' }}>
              Unscoped work has been logged to <strong>{engagementName}</strong> for{' '}
              <strong>{clientName}</strong>. The engagement is now{' '}
              <span style={{ color: badgeColor, fontWeight: '600' }}>
                {budgetConsumedPercent.toFixed(0)}% over budget
              </span>
              .
            </Text>

            {/* Key Metrics */}
            <Section style={{ marginBottom: '24px' }}>
              <Row
                style={{
                  backgroundColor: '#f3f4f6',
                  padding: '12px 16px',
                  marginBottom: '8px',
                  borderRadius: '6px',
                }}
              >
                <Text style={{ margin: '0', fontSize: '13px', color: '#6b7280' }}>
                  <strong>Unscoped Hours:</strong>
                </Text>
                <Text style={{ margin: '0 0 0 16px', fontSize: '13px', fontWeight: '600', color: '#000' }}>
                  {unscopedHours.toFixed(1)} hours
                </Text>
              </Row>

              <Row
                style={{
                  backgroundColor: '#f3f4f6',
                  padding: '12px 16px',
                  marginBottom: '8px',
                  borderRadius: '6px',
                }}
              >
                <Text style={{ margin: '0', fontSize: '13px', color: '#6b7280' }}>
                  <strong>Estimated Cost:</strong>
                </Text>
                <Text style={{ margin: '0 0 0 16px', fontSize: '13px', fontWeight: '600', color: '#dc2626' }}>
                  ${unscopedAmount.toFixed(2)}
                </Text>
              </Row>

              <Row
                style={{
                  backgroundColor: '#f3f4f6',
                  padding: '12px 16px',
                  marginBottom: '8px',
                  borderRadius: '6px',
                }}
              >
                <Text style={{ margin: '0', fontSize: '13px', color: '#6b7280' }}>
                  <strong>Budget Remaining:</strong>
                </Text>
                <Text style={{ margin: '0 0 0 16px', fontSize: '13px', fontWeight: '600', color: budgetRemaining > 0 ? '#059669' : '#dc2626' }}>
                  ${budgetRemaining.toFixed(2)}
                </Text>
              </Row>
            </Section>

            {/* Time Entries Table */}
            <Section style={{ marginBottom: '24px' }}>
              <Text style={{ margin: '0 0 12px 0', fontSize: '13px', fontWeight: '600', color: '#1f2937' }}>
                Recent Unscoped Entries:
              </Text>

              <table
                style={{
                  width: '100%',
                  borderCollapse: 'collapse',
                  fontSize: '12px',
                }}
              >
                <thead>
                  <tr style={{ borderBottom: '1px solid #e5e7eb', backgroundColor: '#f9fafb' }}>
                    <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: '600', color: '#6b7280' }}>
                      Date
                    </th>
                    <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: '600', color: '#6b7280' }}>
                      Hours
                    </th>
                    <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: '600', color: '#6b7280' }}>
                      Description
                    </th>
                    <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: '600', color: '#6b7280' }}>
                      Logged By
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {timeEntries.slice(0, 10).map((entry, idx) => (
                    <tr
                      key={entry.id}
                      style={{
                        borderBottom: '1px solid #e5e7eb',
                        backgroundColor: idx % 2 === 0 ? '#ffffff' : '#f9fafb',
                      }}
                    >
                      <td style={{ padding: '8px 12px', color: '#374151' }}>
                        {new Date(entry.entry_date).toLocaleDateString('en-US', {
                          month: 'short',
                          day: 'numeric',
                        })}
                      </td>
                      <td style={{ padding: '8px 12px', color: '#374151', fontWeight: '600' }}>
                        {entry.hours.toFixed(1)}
                      </td>
                      <td style={{ padding: '8px 12px', color: '#374151' }}>
                        {entry.description}
                      </td>
                      <td style={{ padding: '8px 12px', color: '#6b7280', fontSize: '11px' }}>
                        {entry.logged_by || '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {timeEntries.length > 10 && (
                <Text style={{ margin: '8px 0 0 0', fontSize: '11px', color: '#6b7280' }}>
                  ... and {timeEntries.length - 10} more entries
                </Text>
              )}
            </Section>

            <Hr style={{ borderColor: '#e5e7eb', margin: '24px 0' }} />

            {/* Action Buttons */}
            <Section style={{ marginBottom: '24px' }}>
              <Text style={{ margin: '0 0 12px 0', fontSize: '13px', fontWeight: '600', color: '#1f2937' }}>
                Next Steps:
              </Text>

              <Row style={{ marginBottom: '12px' }}>
                <Button
                  href={engagementUrl}
                  style={{
                    backgroundColor: '#3b82f6',
                    color: '#ffffff',
                    padding: '10px 20px',
                    borderRadius: '6px',
                    textDecoration: 'none',
                    fontSize: '13px',
                    fontWeight: '600',
                  }}
                >
                  Review Engagement
                </Button>
              </Row>

              {changeOrderUrl && (
                <Row>
                  <Button
                    href={changeOrderUrl}
                    style={{
                      backgroundColor: '#10b981',
                      color: '#ffffff',
                      padding: '10px 20px',
                      borderRadius: '6px',
                      textDecoration: 'none',
                      fontSize: '13px',
                      fontWeight: '600',
                    }}
                  >
                    Generate Change Order
                  </Button>
                </Row>
              )}
            </Section>

            {/* Recommendations */}
            <Section style={{ backgroundColor: '#f0fdf4', padding: '12px 16px', borderRadius: '6px' }}>
              <Text style={{ margin: '0', fontSize: '12px', color: '#166534' }}>
                <strong>💡 Recommendation:</strong> Review these entries with your team and decide whether to:
              </Text>
              <ul style={{ margin: '8px 0 0 16px', fontSize: '12px', color: '#166534', paddingLeft: '16px' }}>
                <li>Include in change order (scope expansion)</li>
                <li>Mark as administrative overhead (not billable)</li>
                <li>Write off as professional courtesy</li>
              </ul>
            </Section>
          </Section>

          {/* Footer */}
          <Section style={{ marginTop: '24px', textAlign: 'center', paddingBottom: '16px' }}>
            <Hr style={{ borderColor: '#e5e7eb', margin: '16px 0' }} />
            <Text style={{ margin: '0', fontSize: '11px', color: '#6b7280' }}>
              You're receiving this email because you're listed as the owner of this engagement.{' '}
              <Link href="#" style={{ color: '#3b82f6', textDecoration: 'underline' }}>
                Update notification preferences
              </Link>
            </Text>
            <Text style={{ margin: '4px 0 0 0', fontSize: '11px', color: '#9ca3af' }}>
              Scope Tracker • {new Date().getFullYear()}
            </Text>
          </Section>
        </Container>
      </Body>
    </Html>
  );
};

export default DriftAlertEmail;

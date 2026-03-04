import React from 'react';
import {
  Body,
  Button,
  Container,
  Head,
  Hr,
  Html,
  Link,
  Preview,
  Row,
  Section,
  Text,
  Font,
} from '@react-email/components';

interface ChangeOrderReadyProps {
  partnerName: string;
  engagementName: string;
  clientName: string;
  matterName: string;
  estimatedAdditionalHours: number;
  estimatedAdditionalCost: number;
  revisedTotalBudget: number;
  scopeAdditions: string[];
  changeOrderUrl: string;
  reviewDeadline?: string;
}

/**
 * Change Order Ready Email Template
 *
 * Notifies partner that a change order has been auto-generated and is ready for review.
 * Includes summary of scope additions and action items.
 */
export const ChangeOrderReadyEmail: React.FC<ChangeOrderReadyProps> = ({
  partnerName,
  engagementName,
  clientName,
  matterName,
  estimatedAdditionalHours,
  estimatedAdditionalCost,
  revisedTotalBudget,
  scopeAdditions,
  changeOrderUrl,
  reviewDeadline,
}) => {
  const formattedDeadline = reviewDeadline
    ? new Date(reviewDeadline).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    : null;

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
        <title>Change Order Ready for Review</title>
      </Head>
      <Preview>
        Change Order ready for {engagementName} - ${estimatedAdditionalCost.toFixed(2)} in
        scope additions
      </Preview>

      <Body style={{ backgroundColor: '#f9fafb' }}>
        <Container style={{ maxWidth: '600px', marginTop: '20px' }}>
          {/* Success Banner */}
          <Section
            style={{
              backgroundColor: '#d1fae5',
              borderLeft: '4px solid #10b981',
              padding: '16px',
              marginBottom: '24px',
              borderRadius: '4px',
            }}
          >
            <Row>
              <Text style={{ margin: '0 0 8px 0', fontSize: '14px', color: '#065f46' }}>
                <strong>✅ Change Order Generated</strong>
              </Text>
            </Row>
            <Row>
              <Text style={{ margin: '0', fontSize: '13px', color: '#047857' }}>
                Ready for review and client communication
              </Text>
            </Row>
          </Section>

          {/* Main Content */}
          <Section style={{ backgroundColor: '#ffffff', padding: '32px', borderRadius: '8px' }}>
            <Text style={{ margin: '0 0 16px 0', fontSize: '16px', fontWeight: '600' }}>
              Hi {partnerName},
            </Text>

            <Text style={{ margin: '0 0 20px 0', fontSize: '14px', lineHeight: '1.6', color: '#374151' }}>
              A change order has been automatically generated for{' '}
              <strong>{engagementName}</strong> ({matterName}). This change order documents the
              scope additions that were detected and need to be addressed with the client.
            </Text>

            {/* Summary Box */}
            <Section
              style={{
                backgroundColor: '#eff6ff',
                padding: '16px',
                borderRadius: '6px',
                marginBottom: '24px',
              }}
            >
              <Row
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  marginBottom: '12px',
                }}
              >
                <Text style={{ margin: '0', fontSize: '13px', color: '#1e40af' }}>
                  <strong>Additional Hours:</strong>
                </Text>
                <Text style={{ margin: '0', fontSize: '13px', fontWeight: '600', color: '#1e40af' }}>
                  {estimatedAdditionalHours} hours
                </Text>
              </Row>

              <Row
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  marginBottom: '12px',
                }}
              >
                <Text style={{ margin: '0', fontSize: '13px', color: '#1e40af' }}>
                  <strong>Additional Cost:</strong>
                </Text>
                <Text style={{ margin: '0', fontSize: '13px', fontWeight: '600', color: '#dc2626' }}>
                  ${estimatedAdditionalCost.toFixed(2)}
                </Text>
              </Row>

              <Hr style={{ borderColor: '#bfdbfe', margin: '12px 0' }} />

              <Row
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                }}
              >
                <Text style={{ margin: '0', fontSize: '14px', fontWeight: '600', color: '#000' }}>
                  Revised Total Budget:
                </Text>
                <Text style={{ margin: '0', fontSize: '14px', fontWeight: '700', color: '#1e40af' }}>
                  ${revisedTotalBudget.toFixed(2)}
                </Text>
              </Row>
            </Section>

            {/* Scope Additions */}
            <Section style={{ marginBottom: '24px' }}>
              <Text style={{ margin: '0 0 12px 0', fontSize: '13px', fontWeight: '600', color: '#1f2937' }}>
                Scope Additions:
              </Text>

              <ul
                style={{
                  margin: '0',
                  paddingLeft: '20px',
                  fontSize: '13px',
                  color: '#374151',
                  lineHeight: '1.6',
                }}
              >
                {scopeAdditions.map((item, idx) => (
                  <li key={idx} style={{ marginBottom: '6px' }}>
                    {item}
                  </li>
                ))}
              </ul>
            </Section>

            <Hr style={{ borderColor: '#e5e7eb', margin: '24px 0' }} />

            {/* Review Instructions */}
            <Section style={{ marginBottom: '24px', backgroundColor: '#fef3c7', padding: '16px', borderRadius: '6px' }}>
              <Text style={{ margin: '0 0 8px 0', fontSize: '12px', fontWeight: '600', color: '#92400e' }}>
                📋 Review Checklist:
              </Text>
              <ul
                style={{
                  margin: '8px 0 0 16px',
                  fontSize: '12px',
                  color: '#78350f',
                  paddingLeft: '16px',
                }}
              >
                <li>Verify scope additions match client requests</li>
                <li>Confirm hours and cost estimates are accurate</li>
                <li>Decide on revised timeline if needed</li>
                <li>Review with team before sending to client</li>
              </ul>
            </Section>

            {/* Action Buttons */}
            <Section style={{ marginBottom: '24px' }}>
              <Row style={{ marginBottom: '12px' }}>
                <Button
                  href={changeOrderUrl}
                  style={{
                    backgroundColor: '#10b981',
                    color: '#ffffff',
                    padding: '12px 24px',
                    borderRadius: '6px',
                    textDecoration: 'none',
                    fontSize: '14px',
                    fontWeight: '600',
                    display: 'inline-block',
                  }}
                >
                  Review Change Order
                </Button>
              </Row>

              <Text style={{ margin: '12px 0 0 0', fontSize: '12px', color: '#6b7280' }}>
                {formattedDeadline && (
                  <>
                    Please review by <strong>{formattedDeadline}</strong> to send to client promptly.
                  </>
                )}
              </Text>
            </Section>

            {/* Status Info */}
            <Section style={{ backgroundColor: '#f3f4f6', padding: '12px 16px', borderRadius: '6px' }}>
              <Text style={{ margin: '0', fontSize: '12px', color: '#4b5563' }}>
                <strong>Status:</strong> Draft (awaiting your review)
              </Text>
              <Text style={{ margin: '4px 0 0 0', fontSize: '12px', color: '#4b5563' }}>
                <strong>Next:</strong> Send to {clientName} for approval → Create invoice
              </Text>
            </Section>
          </Section>

          {/* Footer */}
          <Section style={{ marginTop: '24px', textAlign: 'center', paddingBottom: '16px' }}>
            <Hr style={{ borderColor: '#e5e7eb', margin: '16px 0' }} />
            <Text style={{ margin: '0', fontSize: '11px', color: '#6b7280' }}>
              This change order was auto-generated based on detected scope drift.{' '}
              <Link href="#" style={{ color: '#3b82f6', textDecoration: 'underline' }}>
                Learn more
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

export default ChangeOrderReadyEmail;

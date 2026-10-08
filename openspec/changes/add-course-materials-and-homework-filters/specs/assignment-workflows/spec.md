# Spec Delta

## ADDED Requirements

### Requirement: A posted response links its attachments
The system SHALL post the uploaded attachments as the full attachment objects the backend returned, so the response comment references them; it SHALL NOT send bare attachment ids to the response-comment action. Attachment ids SHALL be used only for the upload-store and cleanup actions.

#### Scenario: Posted comment references its files
- **WHEN** a previewed response with attachments is submitted
- **THEN** the response-comment request carries the full attachment objects and the read-back finds the comment with its attachments linked

#### Scenario: Ids are used only for store and cleanup
- **WHEN** uploaded attachments are finalized or cleaned up
- **THEN** those requests use the attachment ids, not the objects

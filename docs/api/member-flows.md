# Member API Flows

## Signup (Open Enrollment)
1. POST /auth/start-signup — verify org code + CAPTCHA
2. POST /auth/send-code — send 6-digit email verification
3. POST /auth/verify-code — confirm email
4. POST /auth/set-password — create password, member created as pending_payment
5. GET /plans — list published plans
6. POST /payments/pay — create payment intent + activate membership

## Signup (Approved Enrollment)
Steps 1-4 same as open, but member created as pending_approval
5. GET /members/approval-queue — admin views pending
6. POST /members/{id}/approval — admin approves → pending_payment
7. Member proceeds to payment (steps 5-6 from open)

## Signup (Invite-Only)
1. Admin: POST /members/invite — send invite code
2. Prospect: POST /auth/redeem-invite — enter code + set password
3. POST /payments/pay — pay and activate

## Member Management
- GET /members — directory listing
- GET /members/approval-queue — pending approvals
- POST /members/{id}/status — ban/unban/freeze/unfreeze/cancel
- GET /members/freeze-requests — owner/manager queue of pending pause requests
- POST /members/freeze-requests/{request_id}/decision — approve or decline a pause request
- PATCH /members/{id}/role — change role
- PATCH /members/{id}/email — update email
- DELETE /members/{id} — hard delete (owner only)

## Membership Pause Requests
- GET /memberships/me/freeze-requests — list the signed-in member's requests
- POST /memberships/me/freeze-requests — submit a pause request for gym review
- DELETE /memberships/me/freeze-requests/{request_id} — withdraw a pending request
- POST /members/import — bulk CSV import

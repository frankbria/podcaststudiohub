# PodcastStudioHub Testing Guide

This guide provides a step-by-step checklist to test all features of the PodcastStudioHub application (Development Environment).

**Base URL**: https://dev.podcaststudiohub.me
**API URL**: https://dev.podcaststudiohub.me/api

---

## Prerequisites

Before testing, ensure you have:
- [ ] A modern web browser (Chrome, Firefox, Safari, or Edge)
- [ ] Valid test URLs for podcast content (articles, blog posts, YouTube videos)
- [ ] Sample text content for direct input testing
- [ ] Network connection to access external URLs

---

## 1. Landing Page & Public Access

### 1.1 Homepage
- [ ] Navigate to https://dev.podcaststudiohub.me
- [ ] Verify the homepage loads successfully
- [ ] Check that the page displays "Podcastfy Studio" branding
- [ ] Verify navigation links are visible (Login/Sign Up)
- [ ] Check that the page is responsive (resize browser window)

---

## 2. User Authentication

### 2.1 Sign Up (New User Registration)
- [ ] Click "Sign Up" or navigate to `/signup`
- [ ] Verify the sign-up form displays with fields:
  - [ ] Full Name (optional)
  - [ ] Email (required)
  - [ ] Password (required, min 8 characters)
- [ ] Test validation:
  - [ ] Try submitting with empty email (should show error)
  - [ ] Try submitting with invalid email format (should show error)
  - [ ] Try submitting with password < 8 characters (should show error)
- [ ] Create a new account with valid credentials:
  - Email: `test-user-$(date +%s)@example.com`
  - Password: `TestPassword123`
- [ ] Verify success: redirected to login page with "registered=true" message
- [ ] Check "Already have an account? Sign in" link works

### 2.2 Login (Existing User)
- [ ] Navigate to `/login`
- [ ] Verify the login form displays with fields:
  - [ ] Email
  - [ ] Password
- [ ] Test validation:
  - [ ] Try logging in with incorrect credentials (should show error)
  - [ ] Try logging in with non-existent email (should show error)
- [ ] Login with the account created above
- [ ] Verify successful redirect to `/dashboard`
- [ ] Check that session persists (refresh page, should stay logged in)
- [ ] Check "Don't have an account? Sign up" link works

### 2.3 Logout
- [ ] While logged in, find and click logout button
- [ ] Verify redirect to homepage or login page
- [ ] Try accessing `/dashboard` (should redirect to login)

---

## 3. Dashboard & Project Management

### 3.1 Dashboard Overview
- [ ] After login, verify redirect to `/dashboard`
- [ ] Check page displays "My Projects" heading
- [ ] Verify "Create Project" button is visible
- [ ] If no projects exist, check empty state message appears

### 3.2 Create Project
- [ ] Click "Create Project" button
- [ ] Verify modal/dialog opens with form fields:
  - [ ] Project Title (required)
  - [ ] Description (optional)
- [ ] Test validation:
  - [ ] Try submitting with empty title (should prevent or show error)
- [ ] Create a new project:
  - Title: `Test Podcast Project`
  - Description: `A test podcast for quality assurance`
- [ ] Click "Create Project" button
- [ ] Verify modal closes
- [ ] Verify new project appears in dashboard grid
- [ ] Check project card displays:
  - [ ] Project title
  - [ ] Project description
  - [ ] Episode count (should be 0)

### 3.3 View Project
- [ ] Click on a project card
- [ ] Verify redirect to `/projects/{project-id}`
- [ ] Check page displays:
  - [ ] Project title
  - [ ] Project description
  - [ ] "Create Episode" button
  - [ ] "Back to Dashboard" button
- [ ] Click "Back to Dashboard" and verify navigation works

---

## 4. Episode Management

### 4.1 Create Episode
- [ ] From project page, click "Create Episode"
- [ ] Verify dialog opens with:
  - [ ] Episode Title field
- [ ] Create a new episode:
  - Title: `Episode 1: Introduction to Testing`
- [ ] Click "Create Episode"
- [ ] Verify redirect to `/episodes/{episode-id}`

### 4.2 Episode Details Page
- [ ] On episode page, verify display of:
  - [ ] Episode title
  - [ ] Episode description (if any)
  - [ ] Generation status badge (should be "draft")
  - [ ] "Add Content" button
  - [ ] Content sources list (empty initially)
  - [ ] "Back to Project" button

---

## 5. Content Source Management

### 5.1 Add URL Content Source
- [ ] Click "Add Content" button
- [ ] Verify content source dialog opens
- [ ] Select "URL" as source type
- [ ] Test URL content addition:
  - [ ] Enter a valid article URL (e.g., https://example.com/article)
  - [ ] Click "Add Content"
  - [ ] Verify dialog closes
  - [ ] Verify content source appears in list with:
    - [ ] Source type: "url"
    - [ ] URL displayed
    - [ ] Delete button
- [ ] Add another URL source (e.g., a blog post URL)
- [ ] Verify both sources appear in the list

### 5.2 Add Text Content Source
- [ ] Click "Add Content" again
- [ ] Select "Text" as source type
- [ ] Enter sample text content:
  ```
  This is a test podcast script about artificial intelligence.
  AI has revolutionized many industries including healthcare,
  finance, and transportation. Today we'll discuss the key
  developments and future implications.
  ```
- [ ] Click "Add Content"
- [ ] Verify text content source appears with:
  - [ ] Source type: "text"
  - [ ] Truncated preview of text
  - [ ] Delete button

### 5.3 Delete Content Source
- [ ] Click delete button on one of the content sources
- [ ] Verify confirmation dialog or immediate removal
- [ ] Verify content source is removed from list
- [ ] Verify remaining sources are still visible

---

## 6. Podcast Generation

### 6.1 Start Generation
- [ ] Ensure episode has at least one content source
- [ ] Click "Generate Podcast" button
- [ ] Verify button changes to loading state or disables
- [ ] Verify generation status changes from "draft" to "queued"

### 6.2 Monitor Generation Progress
- [ ] Watch for status updates (should auto-refresh via SSE):
  - [ ] Status: "queued" → "extracting" → "generating" → "synthesizing" → "complete"
  - [ ] Progress indicator shows percentage (0-100%)
  - [ ] Progress messages update in real-time
- [ ] Verify each status transition is visible
- [ ] Note: Generation may take 1-5 minutes depending on content length

### 6.3 Generation Failure Handling
**Optional**: Test failure scenarios if you have content that might fail:
- [ ] Try generating with invalid URL
- [ ] Verify status changes to "failed"
- [ ] Check error message is displayed
- [ ] Verify ability to retry generation

---

## 7. Audio Playback

### 7.1 Play Generated Podcast
- [ ] After generation completes (status: "complete")
- [ ] Verify audio player appears on episode page
- [ ] Check audio player controls:
  - [ ] Play/Pause button
  - [ ] Progress bar
  - [ ] Volume control
  - [ ] Current time / Duration display
- [ ] Click play and verify audio starts
- [ ] Test player controls:
  - [ ] Pause audio
  - [ ] Seek to different position
  - [ ] Adjust volume
  - [ ] Verify time display updates

### 7.2 Download Audio
- [ ] Locate download button (if available)
- [ ] Click download
- [ ] Verify audio file downloads to your computer
- [ ] Verify downloaded file plays in local media player
- [ ] Check filename is meaningful (e.g., includes episode title)

---

## 8. API Health & System Status

### 8.1 API Health Check
- [ ] Navigate to https://dev.podcaststudiohub.me/api/health
- [ ] Verify JSON response:
  ```json
  {
    "status": "healthy",
    "version": "0.1.0"
  }
  ```
- [ ] Check HTTP status is 200 OK

### 8.2 API Documentation (if available)
- [ ] Navigate to https://dev.podcaststudiohub.me/api/docs
- [ ] Verify Swagger/OpenAPI documentation loads
- [ ] Browse available endpoints
- [ ] Test authentication flow in API docs

---

## 9. Navigation & User Experience

### 9.1 Navigation Flow
- [ ] Test navigation path: Dashboard → Project → Episode → Back to Project → Back to Dashboard
- [ ] Verify breadcrumbs or back buttons work correctly
- [ ] Test browser back button (should navigate correctly)
- [ ] Verify browser forward button works

### 9.2 Session Persistence
- [ ] While logged in, refresh the page
- [ ] Verify you remain logged in
- [ ] Close browser tab and reopen
- [ ] Navigate back to site
- [ ] Check if session persists (may depend on cookie settings)

### 9.3 Protected Routes
- [ ] Log out
- [ ] Try accessing protected URLs directly:
  - [ ] `/dashboard` - should redirect to login
  - [ ] `/projects/{id}` - should redirect to login
  - [ ] `/episodes/{id}` - should redirect to login
- [ ] Log back in
- [ ] Verify redirect to requested page or dashboard

---

## 10. Responsive Design

### 10.1 Desktop View (1920x1080)
- [ ] Resize browser to full desktop size
- [ ] Verify layout is optimal:
  - [ ] Project cards in grid (2-3 columns)
  - [ ] Forms are centered and appropriately sized
  - [ ] Text is readable
  - [ ] Buttons are appropriately sized

### 10.2 Tablet View (768x1024)
- [ ] Resize browser to tablet width
- [ ] Verify responsive behavior:
  - [ ] Project cards adjust to 1-2 columns
  - [ ] Navigation adapts (hamburger menu if applicable)
  - [ ] Forms remain usable
  - [ ] No horizontal scrolling

### 10.3 Mobile View (375x667)
- [ ] Resize browser to mobile width
- [ ] Verify mobile optimization:
  - [ ] Project cards stack (1 column)
  - [ ] Touch-friendly button sizes
  - [ ] Forms are scrollable and usable
  - [ ] Text remains readable
  - [ ] Audio player is mobile-friendly

---

## 11. Error Handling & Edge Cases

### 11.1 Network Errors
- [ ] With browser DevTools open, throttle network to "Slow 3G"
- [ ] Try loading dashboard
- [ ] Verify loading indicators appear
- [ ] Verify graceful degradation or error messages
- [ ] Restore normal network speed

### 11.2 Invalid Data
- [ ] Try creating project with extremely long title (>1000 chars)
- [ ] Try creating episode with special characters in title
- [ ] Try adding content source with invalid URL format
- [ ] Verify appropriate error messages or validation

### 11.3 Browser Console
- [ ] Open browser DevTools (F12)
- [ ] Navigate through application
- [ ] Check Console tab for errors (should be minimal/none)
- [ ] Check Network tab for failed requests (should be none in happy path)

---

## 12. Multi-Episode Workflow

### 12.1 Create Multiple Episodes
- [ ] Create a second episode in the same project
  - Title: `Episode 2: Advanced Topics`
- [ ] Create a third episode
  - Title: `Episode 3: Best Practices`
- [ ] Return to project page
- [ ] Verify all episodes are listed
- [ ] Verify episode count in dashboard updated

### 12.2 Episode Status Tracking
- [ ] View project page
- [ ] Verify each episode shows correct status:
  - [ ] Draft (no content or not generated)
  - [ ] Queued/Generating (in progress)
  - [ ] Complete (audio available)
  - [ ] Failed (if any errors)

---

## 13. Multiple Projects Workflow

### 13.1 Create Additional Projects
- [ ] From dashboard, create a second project:
  - Title: `Tech News Podcast`
  - Description: `Weekly tech news and analysis`
- [ ] Create a third project:
  - Title: `Interview Series`
  - Description: `Conversations with industry experts`
- [ ] Verify all projects appear in dashboard grid
- [ ] Verify each project shows correct episode count

### 13.2 Project Isolation
- [ ] Create episode in Project 1
- [ ] Navigate to Project 2
- [ ] Verify Project 2's episodes don't include Project 1's episodes
- [ ] Verify data isolation is maintained

---

## 14. Performance Testing

### 14.1 Load Time
- [ ] Measure page load times:
  - [ ] Homepage: < 3 seconds
  - [ ] Dashboard: < 3 seconds
  - [ ] Project page: < 2 seconds
  - [ ] Episode page: < 2 seconds
- [ ] Check using browser DevTools Network tab

### 14.2 Generation Performance
- [ ] Start generation with small content (1 URL or short text)
- [ ] Note time to completion: should be 1-3 minutes
- [ ] Start generation with multiple URLs (3-4 URLs)
- [ ] Note time to completion: should be 3-7 minutes
- [ ] Verify progress updates smoothly (no hanging)

---

## 15. Data Persistence

### 15.1 Project Data
- [ ] Create project with specific title/description
- [ ] Log out
- [ ] Log back in
- [ ] Verify project still exists with correct data

### 15.2 Episode Data
- [ ] Create episode with content sources
- [ ] Close browser completely
- [ ] Reopen browser and log back in
- [ ] Navigate to episode
- [ ] Verify content sources are preserved

### 15.3 Generated Audio
- [ ] Generate a podcast
- [ ] Wait for completion
- [ ] Log out and log back in
- [ ] Navigate to completed episode
- [ ] Verify audio is still available and playable

---

## 16. Cross-Browser Testing

### 16.1 Chrome/Edge
- [ ] Perform core workflow (signup → login → create project → episode → generate)
- [ ] Verify all features work
- [ ] Check for any visual issues

### 16.2 Firefox
- [ ] Repeat core workflow
- [ ] Verify audio player works
- [ ] Check for compatibility issues

### 16.3 Safari (if available)
- [ ] Repeat core workflow
- [ ] Test audio playback specifically
- [ ] Verify Next.js features work properly

---

## 17. Accessibility Testing

### 17.1 Keyboard Navigation
- [ ] Navigate site using only Tab, Enter, and arrow keys
- [ ] Verify all interactive elements are reachable
- [ ] Check focus indicators are visible
- [ ] Test form submission with Enter key

### 17.2 Screen Reader (Optional)
- [ ] Enable screen reader (NVDA, JAWS, or VoiceOver)
- [ ] Navigate through dashboard
- [ ] Verify meaningful labels are announced
- [ ] Test form interaction with screen reader

### 17.3 Color Contrast
- [ ] Check text is readable against backgrounds
- [ ] Verify status badges have sufficient contrast
- [ ] Check button text is clearly visible

---

## 18. Security Testing

### 18.1 Authentication Security
- [ ] Verify you cannot access protected pages when logged out
- [ ] Check that JWT tokens expire appropriately
- [ ] Verify logout clears session
- [ ] Test that refreshing after logout keeps you logged out

### 18.2 Authorization
- [ ] Create project as User A
- [ ] Note project ID
- [ ] Log out and log in as User B
- [ ] Try accessing User A's project URL directly
- [ ] Verify access is denied (403) or project not found (404)

### 18.3 Input Sanitization
- [ ] Try entering HTML/JavaScript in form fields:
  - `<script>alert('XSS')</script>`
  - `<img src=x onerror=alert('XSS')>`
- [ ] Verify content is escaped/sanitized
- [ ] Check that malicious scripts don't execute

---

## 19. Advanced Content Testing

### 19.1 Different Content Types
Test with various content sources:
- [ ] **Blog article**: Add URL to a blog post
- [ ] **News article**: Add URL to a news website
- [ ] **YouTube video**: Add YouTube URL (if supported)
- [ ] **PDF document**: Add PDF URL (if supported)
- [ ] **Long-form text**: Add 2000+ word text content
- [ ] **Short text**: Add 100-word text content

### 19.2 Multiple Content Sources
- [ ] Create episode with 5+ different content sources
- [ ] Generate podcast
- [ ] Verify all content is incorporated
- [ ] Check audio duration is appropriate for content volume

---

## 20. Final Integration Test

### 20.1 Complete End-to-End Workflow
Perform a complete user journey:

1. [ ] Sign up new user
2. [ ] Create first project "My Test Podcast"
3. [ ] Create first episode "Pilot Episode"
4. [ ] Add 2-3 content sources (mix of URLs and text)
5. [ ] Generate podcast
6. [ ] Monitor progress to completion
7. [ ] Play generated audio
8. [ ] Download audio file
9. [ ] Create second episode
10. [ ] Add different content
11. [ ] Generate second podcast
12. [ ] Verify both episodes in project
13. [ ] Return to dashboard
14. [ ] Verify project shows 2 episodes
15. [ ] Log out
16. [ ] Log back in
17. [ ] Verify all data persists
18. [ ] Delete a content source
19. [ ] Verify episode updates correctly
20. [ ] Complete workflow without errors

---

## Test Summary

After completing all tests, document:

**Environment**: https://dev.podcaststudiohub.me
**Test Date**: _____________
**Tester**: _____________
**Browser(s) Tested**: _____________
**OS**: _____________

### Results Summary

- **Total Tests**: _____ / _____
- **Passed**: _____
- **Failed**: _____
- **Blocked**: _____

### Critical Issues Found
(List any blocking or severe issues)

1.
2.
3.

### Minor Issues Found
(List any cosmetic or minor issues)

1.
2.
3.

### Recommendations
(Suggestions for improvements)

1.
2.
3.

---

## Notes

- This testing guide assumes the development environment is stable and all services are running
- Some tests may require API keys to be properly configured on the server
- Generation times may vary based on server load and content complexity
- If any critical test fails, stop testing and report the issue immediately
- For production deployment, repeat all tests in the production environment

---

**Version**: 1.0
**Last Updated**: 2025-10-21
**Deployment**: Development Environment

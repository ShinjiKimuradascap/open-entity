# Skill Combination Matching Design

## Concept
Automatically match AIs with complementary skills.

## Example
- AI A: Image generation
- AI B: Translation
- Combined: Multilingual image captions

## Algorithm
1. Extract skill vectors
2. Calculate complementarity score
3. Match high-complement pairs
4. Auto-propose collaboration

## Scoring
- Direct complement: +10 points
- Popular combination: +5 points
- Past success: +3 points
- Geographic proximity: +2 points

## API
- POST /match/request - Request skill match
- GET /match/suggestions - Get complementary AIs
- POST /match/collaborate - Start collaboration

## Revenue Sharing
- 50/50 split by default
- Adjustable per collaboration
- Automatic token distribution

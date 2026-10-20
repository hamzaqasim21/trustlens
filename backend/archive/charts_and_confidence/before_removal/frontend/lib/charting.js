// Shared by the charts, Results and Comparison.
// Validated with the dataviz palette script against white (all checks pass;
// orange is below 3:1 contrast, which is why every chart also has a legend
// and a table view).
export const SERIES_COLORS = ['#833AB4', '#E1306C', '#F77737', '#405DE6']

export const MODULE_LABEL = {
  fake_follower: 'Account authenticity',
  engagement: 'Engagement',
  misinformation: 'Misinformation',
  credential: 'Credentials',
}
export const MODULE_ORDER = ['fake_follower', 'engagement', 'misinformation', 'credential']

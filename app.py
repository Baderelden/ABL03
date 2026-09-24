import hashlib
import hmac
import html
import json
import os
from pathlib import Path

import openai
import streamlit as st
from assessment import Assessment, PANEL_NAMES, assess, panel_summary, prepare_image

st.set_page_config(page_title='Vehicle damage assessment', page_icon='🚘', layout='wide')

LOGO_PATH = Path(__file__).parent / 'assets' / 'abl-1touch-logo.png'

st.markdown('''
<style>
    :root {
        --abl-navy: #090b78;
        --abl-green: #21bf55;
        --abl-ink: #172033;
        --abl-muted: #637083;
        --abl-soft: #f5f7fb;
    }
    .stApp { background: linear-gradient(180deg, #f7f9fc 0, #ffffff 300px); }
    .block-container { max-width: 1180px; padding-top: 2rem; padding-bottom: 3rem; }
    [data-testid="stSidebar"] { background: #ffffff; border-right: 1px solid #e6eaf0; }
    [data-testid="stSidebar"] [data-testid="stImage"] { margin: 0 auto 0.4rem; }
    .abl-eyebrow {
        color: var(--abl-green); font-size: .78rem; font-weight: 800;
        letter-spacing: .14em; text-transform: uppercase; margin-bottom: .35rem;
    }
    .abl-title {
        color: var(--abl-navy); font-size: clamp(2rem, 4vw, 3.2rem);
        font-weight: 800; line-height: 1.05; letter-spacing: -.035em; margin: 0;
    }
    .abl-subtitle { color: var(--abl-muted); font-size: 1.05rem; margin-top: .65rem; }
    .abl-rule {
        height: 4px; width: 76px; border-radius: 10px;
        background: linear-gradient(90deg, var(--abl-navy), var(--abl-green));
        margin: 1rem 0 1.65rem;
    }
    .abl-section {
        color: var(--abl-navy); font-size: .82rem; font-weight: 800;
        letter-spacing: .1em; text-transform: uppercase; margin: 1rem 0 .35rem;
    }
    div[data-testid="stFileUploader"] {
        background: #ffffff; border: 1px solid #e1e7ef; border-radius: 16px;
        padding: .55rem 1rem .25rem; box-shadow: 0 10px 30px rgba(9,11,120,.05);
    }
    div[data-testid="stMetric"] {
        background: #ffffff; border: 1px solid #e1e7ef; border-radius: 14px;
        padding: 1rem 1.15rem; box-shadow: 0 8px 24px rgba(9,11,120,.045);
    }
    div[data-testid="stMetricValue"] { color: var(--abl-navy); font-weight: 800; }
    .stButton > button[kind="primary"] {
        background: linear-gradient(100deg, var(--abl-navy), #2529a8);
        border: 0; border-radius: 10px; min-height: 3rem; font-weight: 700;
        box-shadow: 0 8px 18px rgba(9,11,120,.18);
    }
    .stButton > button[kind="primary"]:hover { background: #070960; }
    .stDownloadButton > button { border-radius: 10px; border-color: var(--abl-navy); color: var(--abl-navy); }
    [data-testid="stDataFrame"] { border: 1px solid #e1e7ef; border-radius: 12px; overflow: hidden; }
    details { background: #ffffff; border-radius: 12px; border: 1px solid #e6eaf0 !important; }
    .abl-summary {
        background: linear-gradient(110deg, #f0f2ff, #f2fff6);
        border-left: 4px solid var(--abl-green); border-radius: 10px;
        padding: .9rem 1rem; color: var(--abl-ink); margin: .4rem 0 1rem;
    }
</style>
''', unsafe_allow_html=True)


def setting(name, default=''):
    value = os.environ.get(name)
    if value is not None:
        return value
    try:
        return st.secrets.get(name, default)
    except FileNotFoundError:
        return default


def clear_review():
    for key in list(st.session_state):
        if key.startswith('review_'):
            del st.session_state[key]


password = setting('APP_PASSWORD')
if password and not st.session_state.get('authenticated'):
    left, centre, right = st.columns([1, 1.2, 1])
    with centre:
        st.image(str(LOGO_PATH), width=165)
        st.markdown('<div class="abl-title" style="font-size:2rem;text-align:center">Vehicle Assessment</div>',
                    unsafe_allow_html=True)
        st.caption('Secure demonstration access')
    with st.form('login'):
        entered = st.text_input('Demo password', type='password')
        submitted = st.form_submit_button('Open demo')
    if submitted:
        if hmac.compare_digest(entered.encode(), str(password).encode()):
            st.session_state.authenticated = True
            st.rerun()
        st.error('Incorrect password.')
    st.stop()

logo_col, heading_col = st.columns([1, 5], vertical_alignment='center')
with logo_col:
    st.image(str(LOGO_PATH), width=145)
with heading_col:
    st.markdown('<div class="abl-eyebrow">AI-powered visual assessment</div>', unsafe_allow_html=True)
    st.markdown('<h1 class="abl-title">Vehicle Damage Assessment</h1>', unsafe_allow_html=True)
    st.markdown('<div class="abl-subtitle">Upload vehicle photographs to generate a structured initial assessment.</div>',
                unsafe_allow_html=True)
st.markdown('<div class="abl-rule"></div>', unsafe_allow_html=True)

with st.sidebar:
    st.caption('Assessment Console')
    st.divider()
    st.header('Assessment settings')
    model_options = setting('OPENAI_MODELS', ['gpt-4.1-mini', 'gpt-4.1', 'gpt-5-mini', 'gpt-5', 'gpt-6-astra'])
    if isinstance(model_options, str):
        model_options = [m.strip() for m in model_options.split(',') if m.strip()]
    if not model_options:
        model_options = ['gpt-4.1-mini', 'gpt-4.1', 'gpt-5-mini', 'gpt-5', 'gpt-6-astra']
    # model = st.selectbox('LLM engine', model_options)
    model = model_options[0]
    # st.caption('Model access depends on your OpenAI API account.')
    api_key = setting('OPENAI_API_KEY')
    if not api_key:
        api_key = st.text_input('OpenAI API key', type='password', help='Used for this session only.')
    notes = st.text_area('Vehicle details (optional)', max_chars=1500,
                         placeholder='For example: electric SUV, model/year, or large truck.')
    st.caption('Photos are sent to OpenAI when you click Assess vehicle.')
    if st.button('Clear photos and assessment'):
        clear_review()
        st.session_state.pop('report', None)
        st.session_state.upload_generation = st.session_state.get('upload_generation', 0) + 1
        st.rerun()

st.markdown('<div class="abl-section">01 · Vehicle photographs</div>', unsafe_allow_html=True)
files = st.file_uploader('Upload vehicle photos', type=['jpg', 'jpeg', 'png', 'webp'],
                         accept_multiple_files=True,
                         key=f"photos_{st.session_state.get('upload_generation', 0)}")
st.caption('Up to 12 photos • 10 MB per photo • 40 MB total • JPEG, PNG or WebP')
images, errors = [], []
if len(files) > 12:
    errors.append('Please upload no more than 12 photos.')
elif sum(f.size for f in files) > 40 * 1024 * 1024:
    errors.append('Please keep the total upload under 40 MB.')
else:
    columns = st.columns(4)
    for i, f in enumerate(files):
        try:
            data = prepare_image(f.getvalue())
            images.append(data)
            columns[i % 4].image(data, caption=f'Photo {i + 1}: {f.name}', width='stretch')
        except ValueError as exc:
            errors.append(f'{f.name}: {exc}')
for error in errors:
    st.error(error)

# A report is tied to the images, model and notes that produced it.
fingerprint = hashlib.sha256()
for f in files:
    fingerprint.update(hashlib.sha256(f.getvalue()).digest())
fingerprint.update(json.dumps([model, notes, "visual-repair-size-v2"]).encode())
case_id = fingerprint.hexdigest()
if st.session_state.get('report', {}).get('case_id') != case_id:
    clear_review()
    st.session_state.pop('report', None)

st.markdown('<div class="abl-section">02 · Generate assessment</div>', unsafe_allow_html=True)
if st.button('Assess vehicle', type='primary', disabled=not images or bool(errors), width='stretch'):
    clear_review()
    st.session_state.pop('report', None)
    if not api_key:
        st.error('Add an OpenAI API key in the sidebar or in Streamlit secrets.')
    else:
        try:
            with st.spinner('Reviewing all vehicle photos…'):
                with openai.OpenAI(api_key=api_key, timeout=120, max_retries=1) as client:
                    result, usage = assess(client, model, images, notes)
            st.session_state.report = {
                'case_id': case_id, 'model': model,
                'assessment': result.model_dump(mode='json'), 'usage': usage,
            }
        except openai.AuthenticationError:
            st.error('The API key was not accepted. Check your OpenAI API key.')
        except openai.RateLimitError:
            st.error('API quota or rate limit reached. Check billing/limits, then retry.')
        except (openai.NotFoundError, openai.PermissionDeniedError):
            st.error('This model is unavailable to your API account. Choose another model.')
        except openai.BadRequestError:
            st.error('The API rejected this request. Check that the selected model supports images and structured outputs.')
        except openai.APIConnectionError:
            st.error('Could not connect to OpenAI, or the request timed out. Please retry.')
        except openai.APIError:
            st.error('OpenAI could not complete the assessment. Please try again later.')
        except ValueError:
            st.error('No valid, complete assessment was returned. Try clearer photos or another model.')

if 'report' in st.session_state:
    report = st.session_state.report
    result = Assessment.model_validate(report['assessment'])
    count, size = panel_summary(result)
    st.divider()
    st.markdown('<div class="abl-section">03 · Assessment results</div>', unsafe_allow_html=True)
    if result.status != 'Assessable':
        st.warning(result.status)
    low, high = result.labour.minimum_hours, result.labour.maximum_hours
    hours = f'{low:g}–{high:g} h' if low is not None else 'Not estimable'
    st.subheader('AI suggestion')
    a, b, c = st.columns(3)
    ai_colour, ai_background = {'Small': ('#166534', '#dcfce7'),
                               'Medium': ('#9a3412', '#ffedd5'),
                               'Large': ('#991b1b', '#fee2e2')}.get(size, ('#334155', '#f1f5f9'))
    a.markdown(f'<div style="background:{ai_background};color:{ai_colour};border:1px solid {ai_colour};'
               f'border-radius:14px;padding:1rem 1.15rem">Repair size<br>'
               f'<strong style="font-size:1.9rem">{html.escape(size)}</strong></div>',
               unsafe_allow_html=True)
    b.metric('Damaged panels', count)
    c.metric('Estimated labour', hours)
    st.caption('Based on visible severity, deformation and likely repair complexity. Panel count is descriptive only.')
    st.caption('Size confidence: ' + result.repair_size.confidence + ' · Evidence photos: ' +
               (', '.join(map(str, result.repair_size.photo_numbers)) or 'None'))
    st.write(f'Vehicle: {result.vehicle_type} · Powertrain: {result.powertrain}')
    st.divider()
    st.subheader('Review and adjust')
    st.caption('Changes are included in the download. No additional AI request is made.')
    st.button('Reset to AI suggestions', on_click=clear_review)
    original_combined_text = '\n\n'.join([result.short_description, result.repair_size.explanation,
                                          result.labour.basis_and_assumptions])
    edited_description = st.text_area('Short description, size explanation and labour assumptions', value=original_combined_text,
                                       height=180, key='review_description_size_and_labour',
                                       help='Edit the AI suggestion. Your wording is included in the downloaded assessment.')
    size_options = ['Small', 'Medium', 'Large', 'No visible damage', 'Not assessable']
    size_labels = {'Small': '🟢 Small', 'Medium': '🟠 Medium', 'Large': '🔴 Large',
                   'No visible damage': 'No visible damage', 'Not assessable': 'Not assessable'}
    left, right = st.columns(2)
    selected_size = left.selectbox('Repair size', size_options, index=size_options.index(size),
                                   format_func=lambda value: size_labels[value], key='review_size')
    panel_options = list(range(13)) + ['13 or more']
    selected_panels = right.selectbox('Number of damaged panels', panel_options,
                                      index=count if count <= 12 else 13, key='review_panels')
    if selected_panels == '13 or more':
        selected_panels = st.number_input('Exact panel count (13 or more)', min_value=13,
                                          value=max(13, count), step=1, key='review_panel_exact')
    has_hours = st.checkbox('Provide a labour-hours estimate', value=low is not None,
                            key='review_has_hours')
    edited_low = edited_high = None
    valid_hours = True
    if has_hours:
        left, right = st.columns(2)
        edited_low = left.number_input('Minimum labour hours', min_value=0.0,
                                       value=float(low or 0), step=0.5, key='review_low')
        edited_high = right.number_input('Maximum labour hours', min_value=0.0,
                                         value=float(high or 0), step=0.5, key='review_high')
        valid_hours = edited_high >= edited_low
        if not valid_hours:
            st.error('Maximum hours must be at least the minimum. Correct the range to enable download.')
        st.caption('Use the same value in both boxes for a single estimate. Hours mean active labour, not elapsed workshop time.')
    review_note = st.text_area('Reviewer notes (optional)', key='review_note', max_chars=1500,
                               placeholder='Briefly explain any changes to the AI suggestion.')
    changed = (selected_size != size or selected_panels != count or
               edited_low != low or edited_high != high or
               edited_description != original_combined_text)
    st.caption('User-adjusted estimate' if changed else 'Estimate matches the AI suggestion')
    st.divider()
    st.subheader('Parts and damage — AI findings')
    st.caption('Manual panel-count changes do not alter this original parts list.')
    if result.damaged_parts:
        st.dataframe([
            {'Part': p.part.value, 'Damage': p.damage, 'Finding': p.certainty,
             'Photo(s)': ', '.join(map(str, p.photo_numbers)),
             'Panel counted': 'Yes' if p.part.value in PANEL_NAMES and p.certainty == 'Observed' else 'No'}
            for p in result.damaged_parts
        ], hide_index=True, width='stretch')
    else:
        st.info('No damaged parts could be confirmed from these photos.')
    st.subheader('Special needs')
    if result.special_needs:
        for need in result.special_needs:
            st.write(f'• {need.requirement} — {need.reason} ({need.basis})')
    else:
        st.write('None identified from the available evidence; vehicle details may still need confirmation.')
    if result.limitations or result.additional_photos_needed:
        with st.expander('Limitations and useful additional photos', expanded=True):
            for item in result.limitations:
                st.write('• ' + item)
            for item in result.additional_photos_needed:
                st.write('• Additional photo: ' + item)
    payload = dict(report, description_and_size_explanation=edited_description,
                   panel_count=selected_panels, damage_size=selected_size,
                   sizing_method='user_reviewed' if changed else 'visual_severity_and_complexity_v2',
                   reviewed_estimate={'description_and_size_explanation': edited_description,
                                      'repair_size': selected_size, 'panel_count': selected_panels,
                                      'minimum_hours': edited_low, 'maximum_hours': edited_high,
                                      'modified_by_user': changed, 'reviewer_notes': review_note},
                   original_ai_summary={'short_description': result.short_description,
                                        'size_explanation': result.repair_size.explanation,
                                        'labour_assumptions': result.labour.basis_and_assumptions,
                                        'repair_size': size, 'panel_count': count,
                                        'minimum_hours': low, 'maximum_hours': high})
    payload.pop('case_id')
    st.download_button('Download assessment (JSON)', json.dumps(payload, indent=2, ensure_ascii=False),
                       file_name='vehicle-assessment.json', mime='application/json', disabled=not valid_hours)
    st.caption('The download includes your reviewed estimate and the unchanged original AI assessment. '
               'Edits are held only in this session; download them before clearing or leaving the app.')
    with st.expander('Model and usage'):
        st.write(report['model'])
        st.json(report['usage'] or {})

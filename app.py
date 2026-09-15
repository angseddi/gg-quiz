import streamlit as st
from supabase import create_client
from streamlit_autorefresh import st_autorefresh
import time
import pandas as pd

# --- 1. Supabase 연결 ---
@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

# --- 2. 실시간 자동 새로고침 (2초마다) ---
st_autorefresh(interval=2000, key="quiz_refresher")

# --- 3. 유틸리티 함수 ---
def get_room_state():
    return supabase.table("quiz_room").select("*").eq("id", 1).execute().data[0]

def get_questions():
    data = supabase.table("questions").select("*").order("q_index").execute().data
    return data

def check_all_submitted(current_q_index):
    players = supabase.table("players").select("*").execute().data
    subs = supabase.table("submissions").select("*").eq("q_index", current_q_index).execute().data
    
    # 참가자가 최소 1명 이상이고, 제출자 수가 참가자 수와 같거나 크면 다음 문제로
    if len(players) > 0 and len(subs) >= len(players):
        time.sleep(1) # 제출 완료 화면을 잠깐 보여주기 위한 딜레이
        supabase.table("quiz_room").update({"current_index": current_q_index + 1}).eq("id", 1).execute()

# --- 4. 화면 구성 ---
st.title("🏆 n/n Case Review 퀴즈쇼")

# 상태 불러오기
room = get_room_state()
questions = get_questions()
total_q = len(questions)

# 사이드바: 역할 선택
role = st.sidebar.radio("접속 권한을 선택하세요", ["참가자 (Player)", "출제자 (Host)"])

# ==========================================
# [출제자 모드]
# ==========================================
if role == "출제자 (Host)":
    pwd = st.sidebar.text_input("출제자 비밀번호", type="password")
    
    if pwd != room["host_pwd"]:
        st.warning("출제자 비밀번호를 입력해주세요.")
    else:
        st.sidebar.success("출제자 인증 완료!")
        
        # 아직 퀴즈 시작 전이면 문제 출제 화면
        if not room["is_started"]:
            st.subheader("🛠️ 문제 출제 및 수정")
            
            with st.expander("새 문제 추가하기"):
                q_idx = st.number_input("문제 번호", min_value=1, value=total_q + 1)
                q_type = st.radio("문제 유형", ["객관식", "주관식"])
                q_text = st.text_area("문제 내용")
                img_url = st.text_input("이미지 URL (선택사항, 구글 이미지 링크 등)")
                
                if q_type == "객관식":
                    options = st.text_input("보기 (쉼표로 구분. 예: 사과,바나나,포도)")
                    ans = st.text_input("정답 (보기 중 하나와 정확히 일치하게 입력)")
                else:
                    options = ""
                    ans = st.text_input("정답 입력")
                    
                if st.button("문제 저장"):
                    supabase.table("questions").upsert({
                        "q_index": q_idx, "q_type": q_type, "q_text": q_text, 
                        "img_url": img_url, "options": options, "answer": ans
                    }).execute()
                    st.success("문제가 저장되었습니다!")
            
            # 참가자 대기 현황
            players = supabase.table("players").select("*").execute().data
            st.write(f"현재 접속한 참가자: **{len(players)}명**")
            
            if st.button("🚀 퀴즈쇼 시작하기", use_container_width=True):
                supabase.table("quiz_room").update({"is_started": True, "current_index": 1}).eq("id", 1).execute()
        
        # 퀴즈 진행 중 관전 화면
        else:
            st.subheader("👀 실시간 관전 모드")
            if room["current_index"] > total_q:
                st.success("모든 퀴즈가 종료되었습니다!")
                if st.button("퀴즈쇼 초기화 (다시 시작)"):
                    supabase.table("quiz_room").update({"is_started": False, "current_index": 1}).eq("id", 1).execute()
                    supabase.table("players").delete().neq("name", "dummy").execute()
                    supabase.table("submissions").delete().neq("id", 0).execute()
            else:
                st.write(f"### 현재 진행 중: {room['current_index']}번 문제")
                st.progress(room["current_index"] / total_q)
                
                subs = supabase.table("submissions").select("*").eq("q_index", room['current_index']).execute().data
                st.write(f"제출 현황: {len(subs)}명 제출 완료")
                for s in subs:
                    st.write(f"✅ {s['player_name']} 제출 완료")
                
                st.warning("참가자 전원이 제출하면 자동으로 다음 문제로 넘어갑니다.")

# ==========================================
# [참가자 모드]
# ==========================================
elif role == "참가자 (Player)":
    
    # 닉네임 입력 전
    if "player_name" not in st.session_state:
        st.subheader("입장하기")
        p_name = st.text_input("사용할 닉네임을 입력하세요")
        if st.button("입장"):
            if p_name:
                supabase.table("players").upsert({"name": p_name}).execute()
                st.session_state["player_name"] = p_name
            else:
                st.error("닉네임을 입력해주세요.")
    
    # 닉네임 입력 후 (로비 또는 게임 진행)
    else:
        p_name = st.session_state["player_name"]
        st.write(f"👤 **{p_name}**님 환영합니다!")
        
        # 1. 퀴즈 시작 전 (대기실)
        if not room["is_started"]:
            st.info("⏳ 출제자가 퀴즈쇼를 시작할 때까지 대기해주세요...")
            
            players = supabase.table("players").select("*").execute().data
            st.write("---")
            st.write("현재 입장한 사람들:")
            for p in players:
                st.write(f"- {p['name']}")
                
        # 2. 퀴즈 진행 중
        elif room["is_started"] and room["current_index"] <= total_q:
            cur_q_idx = room["current_index"]
            q_data = next((item for item in questions if item["q_index"] == cur_q_idx), None)
            
            if q_data:
                st.write("---")
                st.subheader(f"Q{cur_q_idx}. {q_data['q_text']}")
                
                if q_data['img_url']:
                    st.image(q_data['img_url'], use_container_width=True)
                
                # 이미 제출했는지 확인
                my_sub = supabase.table("submissions").select("*").eq("player_name", p_name).eq("q_index", cur_q_idx).execute().data
                
                if my_sub:
                    st.success("✅ 제출 완료! 다른 참가자들이 모두 풀 때까지 대기해주세요.")
                    check_all_submitted(cur_q_idx) # 자동 넘김 체크 로직 실행
                else:
                    # 문제 풀기 폼
                    with st.form(key=f"form_{cur_q_idx}"):
                        if q_data["q_type"] == "객관식":
                            opt_list = [x.strip() for x in q_data["options"].split(",")]
                            user_ans = st.radio("정답을 선택하세요", opt_list)
                        else:
                            user_ans = st.text_input("정답을 입력하세요")
                            
                        submit_btn = st.form_submit_button("제출하기")
                        
                        if submit_btn:
                            is_correct = (user_ans.strip() == q_data["answer"].strip())
                            supabase.table("submissions").insert({
                                "player_name": p_name,
                                "q_index": cur_q_idx,
                                "submitted_answer": user_ans,
                                "is_correct": is_correct
                            }).execute()
                            st.rerun() # 화면 즉시 갱신
                            
        # 3. 퀴즈 종료 (결과 화면)
        elif room["is_started"] and room["current_index"] > total_q:
            st.balloons()
            st.subheader("🎉 퀴즈쇼 종료! 최종 결과 🎉")
            
            # 점수 계산 로직
            subs = supabase.table("submissions").select("*").execute().data
            df = pd.DataFrame(subs)
            if not df.empty:
                # 정답 수 기준 정렬, 정답 수가 같으면 제출 시간이 빠른 순(created_at)
                correct_df = df[df['is_correct'] == True]
                leaderboard = correct_df.groupby('player_name').size().reset_index(name='score')
                
                # 순위 표시
                leaderboard = leaderboard.sort_values(by='score', ascending=False).reset_index(drop=True)
                
                for i, row in leaderboard.iterrows():
                    medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "🔹"
                    st.markdown(f"### {medal} {i+1}등: {row['player_name']} ({row['score']}문제 정답)")
            else:
                st.write("제출된 정답이 없습니다.")

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

# 🌟 스마트 새로고침 통제 변수
needs_refresh = False

st.title("🏆 Case Review 퀴즈쇼")

# DB 데이터 가져오기
try:
    rooms_data = supabase.table("quiz_room").select("*").order("created_at", desc=True).execute().data
except Exception as e:
    st.error("데이터베이스 연결 중입니다...")
    st.stop()

tab1, tab2 = st.tabs(["🙋‍♂️ 퀴즈 참가하기", "👨‍🏫 출제자 메뉴"])

# ==========================================
# [TAB 1: 참가자 모드]
# ==========================================
with tab1:
    if not rooms_data:
        st.info("현재 열려있는 퀴즈쇼가 없습니다. 출제자가 방을 먼저 만들어야 합니다.")
    else:
        room_options = {f"[{r['quiz_title']}] (출제자: {r['host_name']})": r['room_id'] for r in rooms_data}
        selected_room_name = st.selectbox("참가할 퀴즈쇼를 선택하세요", list(room_options.keys()), key="player_room_select")
        sel_room_id = room_options[selected_room_name]
        current_room = next(r for r in rooms_data if r['room_id'] == sel_room_id)

        # 1. 닉네임 입력
        if f"player_name_{sel_room_id}" not in st.session_state:
            st.write("---")
            p_name = st.text_input("사용할 닉네임을 입력하세요")
            if st.button("방 입장하기"):
                if p_name:
                    existing_player = supabase.table("players").select("*").eq("room_id", sel_room_id).eq("player_name", p_name).execute().data
                    if not existing_player:
                        supabase.table("players").insert({"room_id": sel_room_id, "player_name": p_name}).execute()
                    
                    st.session_state[f"player_name_{sel_room_id}"] = p_name
                    st.rerun()
                else:
                    st.warning("닉네임을 입력해주세요.")
        
        # 2. 방 입장 완료 후
        else:
            p_name = st.session_state[f"player_name_{sel_room_id}"]
            st.success(f"👤 **{p_name}**님 입장 완료! (재접속 시 이어서 풀 수 있습니다)")
            
            total_questions = len(supabase.table("questions").select("id").eq("room_id", sel_room_id).execute().data)

            # [대기실]
            if not current_room["is_started"]:
                needs_refresh = True 
                st.info("⏳ 출제자가 퀴즈쇼를 시작할 때까지 대기해주세요...")
                players = supabase.table("players").select("*").eq("room_id", sel_room_id).execute().data
                st.write(f"현재 입장 인원: **{len(players)}명**")
                for p in players:
                    st.write(f"- {p['player_name']}")
            
            # [게임 진행] 
            elif current_room["is_started"] and current_room["current_index"] <= total_questions:
                cur_q_idx = current_room["current_index"]
                q_data = supabase.table("questions").select("*").eq("room_id", sel_room_id).eq("q_index", cur_q_idx).execute().data[0]
                
                st.write("---")
                st.subheader(f"Q{cur_q_idx}. {q_data['q_text']}")
                if q_data['img_url']:
                    st.image(q_data['img_url'], use_container_width=True)
                
                my_sub = supabase.table("submissions").select("*").eq("room_id", sel_room_id).eq("player_name", p_name).eq("q_index", cur_q_idx).execute().data
                
                if my_sub:
                    needs_refresh = True
                    st.success("✅ 제출 완료! 다른 참가자들이 모두 풀 때까지 대기해주세요.")
                    
                    all_players = supabase.table("players").select("*").eq("room_id", sel_room_id).execute().data
                    all_subs = supabase.table("submissions").select("*").eq("room_id", sel_room_id).eq("q_index", cur_q_idx).execute().data
                    
                    sub_names = [s['player_name'] for s in all_subs]
                    unsub_names = [p['player_name'] for p in all_players if p['player_name'] not in sub_names]
                    
                    st.info(f"👀 현재 아직 풀고 있는 사람: **{', '.join(unsub_names) if unsub_names else '없음'}**")
                    
                    if len(all_players) > 0 and len(all_subs) >= len(all_players):
                        time.sleep(1)
                        supabase.table("quiz_room").update({"current_index": cur_q_idx + 1}).eq("room_id", sel_room_id).execute()
                        st.rerun()
                else:
                    with st.form(key=f"form_{sel_room_id}_{cur_q_idx}"):
                        if q_data["q_type"] == "객관식":
                            opt_list = [x.strip() for x in q_data["options"].split(",")]
                            user_ans = st.radio("정답을 선택하세요", opt_list)
                        else:
                            user_ans = st.text_input("정답을 입력하세요")
                            
                        if st.form_submit_button("제출하기"):
                            is_correct = (user_ans.strip() == q_data["answer"].strip())
                            supabase.table("submissions").insert({
                                "room_id": sel_room_id,
                                "player_name": p_name,
                                "q_index": cur_q_idx,
                                "submitted_answer": user_ans,
                                "is_correct": is_correct
                            }).execute()
                            st.rerun()
                            
            # [결과 화면] 
            elif current_room["is_started"] and current_room["current_index"] > total_questions:
                st.balloons()
                st.subheader("🎉 퀴즈쇼 종료! 최종 결과 🎉")
                subs = supabase.table("submissions").select("*").eq("room_id", sel_room_id).execute().data
                df = pd.DataFrame(subs)
                if not df.empty:
                    correct_df = df[df['is_correct'] == True]
                    if not correct_df.empty:
                        leaderboard = correct_df.groupby('player_name').size().reset_index(name='score')
                        leaderboard = leaderboard.sort_values(by='score', ascending=False).reset_index(drop=True)
                        for i, row in leaderboard.iterrows():
                            medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "🔹"
                            st.markdown(f"### {medal} {i+1}등: {row['player_name']} ({row['score']}문제 정답)")
                    else:
                        st.write("정답자가 없습니다 😭")
                else:
                    st.write("제출된 답안이 없습니다.")


# ==========================================
# [TAB 2: 출제자 모드]
# ==========================================
with tab2:
    if "host_room_id" not in st.session_state:
        host_action = st.radio("메뉴 선택", ["새로운 퀴즈쇼 만들기", "기존 퀴즈쇼 관리하기 (로그인)"])
        
        if host_action == "새로운 퀴즈쇼 만들기":
            with st.form("new_room_form", clear_on_submit=True):
                new_title = st.text_input("퀴즈쇼 제목 (예: 9월 3주차 Case)")
                new_host = st.text_input("출제자 이름 (예: 홍길동)")
                new_pwd = st.text_input("이 방의 관리자 비밀번호 설정", type="password")
                
                if st.form_submit_button("방 만들기"):
                    if new_title and new_host and new_pwd:
                        supabase.table("quiz_room").insert({
                            "quiz_title": new_title, "host_name": new_host, "host_pwd": new_pwd
                        }).execute()
                        st.success("✅ 방이 생성되었습니다! 위의 메뉴를 '기존 퀴즈쇼 관리하기'로 변경하여 로그인해주세요.")
                    else:
                        st.error("모든 항목을 입력해주세요.")
        else: 
            if not rooms_data:
                st.warning("아직 만들어진 퀴즈쇼가 없습니다. 방을 먼저 만들어주세요.")
            else:
                room_options = {f"[{r['quiz_title']}] (출제자: {r['host_name']})": r['room_id'] for r in rooms_data}
                host_selected_name = st.selectbox("관리할 퀴즈쇼 선택", list(room_options.keys()))
                host_sel_id = room_options[host_selected_name]
                host_pwd_input = st.text_input("비밀번호 입력", type="password")
                
                if st.button("출제자 로그인"):
                    target_room = next(r for r in rooms_data if r['room_id'] == host_sel_id)
                    if host_pwd_input == target_room['host_pwd']:
                        st.session_state["host_room_id"] = host_sel_id
                        st.rerun()
                    else:
                        st.error("비밀번호가 틀렸습니다!")
    
    else:
        h_room_id = st.session_state["host_room_id"]
        h_room = next((r for r in rooms_data if r['room_id'] == h_room_id), None)
        
        if not h_room:
            del st.session_state["host_room_id"]
            st.rerun()

        st.write(f"### 👑 [{h_room['quiz_title']}] 관리자 패널")
        if st.button("로그아웃 (방 나가기)"):
            del st.session_state["host_room_id"]
            st.rerun()
            
        st.write("---")
        
        questions = supabase.table("questions").select("*").eq("room_id", h_room_id).order("q_index").execute().data
        total_q = len(questions)

        if not h_room["is_started"]:
            st.subheader("📝 퀴즈 문제 만들기")
            
            if total_q > 0:
                with st.expander(f"✅ 지금까지 저장된 문제 확인하기 (총 {total_q}개)"):
                    for q in questions:
                        st.write(f"**Q{q['q_index']}.** {q['q_text']} (정답: {q['answer']})")
            else:
                st.info("아직 등록된 문제가 없습니다. 첫 번째 문제를 만들어주세요!")

            st.write(f"#### ✨ {total_q + 1}번 문제 추가하기")
            with st.form("add_question_form", clear_on_submit=True):
                q_type = st.radio("문제 유형", ["객관식", "주관식"])
                q_text = st.text_area("문제 내용")
                img_url = st.text_input("이미지 URL (선택사항)")
                options = st.text_input("객관식 보기 (쉼표로 구분, 주관식은 비워둠)")
                answer = st.text_input("정답 입력 (객관식은 보기 중 하나와 정확히 일치해야 함)")
                
                submit_btn = st.form_submit_button(f"{total_q + 1}번 문제 저장하고 다음 칸 비우기 ➔")
                
                if submit_btn:
                    if not q_text or not answer:
                        st.error("문제 내용과 정답은 필수입니다!")
                    else:
                        supabase.table("questions").insert({
                            "room_id": h_room_id, "q_index": total_q + 1, "q_type": q_type,
                            "q_text": q_text, "img_url": img_url, "options": options, "answer": answer
                        }).execute()
                        st.success(f"저장 성공! {total_q + 2}번 문제를 작성해주세요.")
                        st.rerun()
            
            st.write("---")
            col1, col2 = st.columns([3, 1])
            players = supabase.table("players").select("*").eq("room_id", h_room_id).execute().data
            with col1:
                st.write(f"👥 현재 대기실 접속자: **{len(players)}명**")
            with col2:
                if st.button("🔄 인원 새로고침"):
                    st.rerun()
            
            if total_q > 0:
                if st.button("🚀 퀴즈쇼 시작하기", type="primary", use_container_width=True):
                    supabase.table("quiz_room").update({"is_started": True, "current_index": 1}).eq("room_id", h_room_id).execute()
                    st.rerun()
            else:
                st.warning("문제를 최소 1개 이상 만들어야 시작할 수 있습니다.")

        else:
            needs_refresh = True
            st.subheader("👀 실시간 관전 모드")
            if h_room["current_index"] > total_q:
                st.success("🎉 모든 퀴즈가 종료되었습니다!")
            else:
                st.write(f"### 현재 진행 중: {h_room['current_index']}번 문제")
                st.progress(h_room["current_index"] / total_q)
                
                all_players = supabase.table("players").select("*").eq("room_id", h_room_id).execute().data
                subs = supabase.table("submissions").select("*").eq("room_id", h_room_id).eq("q_index", h_room['current_index']).execute().data
                
                sub_names = [s['player_name'] for s in subs]
                unsub_names = [p['player_name'] for p in all_players if p['player_name'] not in sub_names]
                
                st.write(f"✅ **제출 완료 ({len(sub_names)}명):** {', '.join(sub_names) if sub_names else '없음'}")
                st.error(f"⏳ **미제출 대기자 ({len(unsub_names)}명):** {', '.join(unsub_names) if unsub_names else '없음'}")

        # 💡 방 완전 삭제 기능 추가
        st.write("---")
        with st.expander("🚨 퀴즈쇼 방 완전 삭제 (위험)"):
            st.warning("이 방에 등록된 문제, 참가자, 제출 내역이 모두 영구적으로 삭제됩니다. 복구할 수 없습니다.")
            if st.button("🗑️ 이 방 삭제하기", type="primary"):
                # 관련된 모든 데이터 싹쓸이 삭제
                supabase.table("submissions").delete().eq("room_id", h_room_id).execute()
                supabase.table("players").delete().eq("room_id", h_room_id).execute()
                supabase.table("questions").delete().eq("room_id", h_room_id).execute()
                supabase.table("quiz_room").delete().eq("room_id", h_room_id).execute()
                
                del st.session_state["host_room_id"] # 로그인 풀기
                st.rerun()

# ==========================================
# 🌟 똑똑한 자동 새로고침 실행기
# ==========================================
if needs_refresh:
    st_autorefresh(interval=2000, key="smart_refresher")
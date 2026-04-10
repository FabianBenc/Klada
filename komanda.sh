#!/bin/bash

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL="http://127.0.0.1:5000"   # Change if hosted elsewhere
USERNAME="admin"
PASSWORD="password123"
COOKIE_JAR=$(mktemp /tmp/psk_cookies.XXXXXX)

# ── Bet URLs ──────────────────────────────────────────────────────────────────
# Add one URL per line between the parentheses
TICKETS=(
    "https://applink.psk.hr/ticketdetail?id=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUEhXOEtHMzk3RzAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.rxSJRsUaH4GQo3hqw7OJz3kOMpYVx3Lt5T2im_TKkkA&source=SB&deeplink=ftnhr%3A%2F%2Fbetslip-history%2Fdetail%3Fid%3DeyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUEhXOEtHMzk3RzAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.rxSJRsUaH4GQo3hqw7OJz3kOMpYVx3Lt5T2im_TKkkA%26source%3DSB"
    "https://applink.psk.hr/ticketdetail?id=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUEtWUktaUzk3RzAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.-diqlXcrCvDExV3Emu8ioLjLwYk8gPmH8Wa4YRjsWN0&source=SB&deeplink=ftnhr%3A%2F%2Fbetslip-history%2Fdetail%3Fid%3DeyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUEtWUktaUzk3RzAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.-diqlXcrCvDExV3Emu8ioLjLwYk8gPmH8Wa4YRjsWN0%26source%3DSB"
    "https://applink.psk.hr/ticketdetail?id=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUFBEWEozUTlBMDAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.L1We5U9y6PoYRKfGMqU8CoZtCHJb6VCV55M8W7XkuIU&source=SB&deeplink=ftnhr%3A%2F%2Fbetslip-history%2Fdetail%3Fid%3DeyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUFBEWEozUTlBMDAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.L1We5U9y6PoYRKfGMqU8CoZtCHJb6VCV55M8W7XkuIU%26source%3DSB"
    "https://applink.psk.hr/ticketdetail?id=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUFJCWUZTSjFBMDAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.Iyj8MKY2Yxchp-eOK311LmFqyVDPtDwSU1DkNEY8ZRs&source=SB&deeplink=ftnhr%3A%2F%2Fbetslip-history%2Fdetail%3Fid%3DeyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUFJCWUZTSjFBMDAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.Iyj8MKY2Yxchp-eOK311LmFqyVDPtDwSU1DkNEY8ZRs%26source%3DSB"
    "https://applink.psk.hr/ticketdetail?id=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUFRZNVExVjFDMDAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.aeoe1WYYQqeydlY2AXXZK8rrsWOjJHgL2I6DByRlSuo&source=SB&deeplink=ftnhr%3A%2F%2Fbetslip-history%2Fdetail%3Fid%3DeyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUFRZNVExVjFDMDAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.aeoe1WYYQqeydlY2AXXZK8rrsWOjJHgL2I6DByRlSuo%26source%3DSB"
    "https://applink.psk.hr/ticketdetail?id=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUFdXWkpSMlNDRzAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.KcOU06NGSMea9FQcW3mA1dg3oI09VHZ3f_P7QT7kX1I&source=SB&deeplink=ftnhr%3A%2F%2Fbetslip-history%2Fdetail%3Fid%3DeyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUFdXWkpSMlNDRzAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.KcOU06NGSMea9FQcW3mA1dg3oI09VHZ3f_P7QT7kX1I%26source%3DSB"
    "https://applink.psk.hr/ticketdetail?id=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUFpFQjBXSzFDODAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.lNP6gvxSyeJWwKC9RNXm2f9ttW5QFZwjYCo12QhGBnQ&source=SB&deeplink=ftnhr%3A%2F%2Fbetslip-history%2Fdetail%3Fid%3DeyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUFpFQjBXSzFDODAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.lNP6gvxSyeJWwKC9RNXm2f9ttW5QFZwjYCo12QhGBnQ%26source%3DSB"
    "https://applink.psk.hr/ticketdetail?id=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUTFDMUs2WVNEODAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.akrAiQd3wqC05lUXsrbcu-I29K_1W4KsprfZ2zXeack&source=SB&deeplink=ftnhr%3A%2F%2Fbetslip-history%2Fdetail%3Fid%3DeyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUTFDMUs2WVNEODAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.akrAiQd3wqC05lUXsrbcu-I29K_1W4KsprfZ2zXeack%26source%3DSB"
    "https://applink.psk.hr/ticketdetail?id=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUTQxMUVTVlNEUjAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.USyWtik_M1Vz2wMwmJlGLgCmE7GnQY3lKJes04SqocE&source=SB&deeplink=ftnhr%3A%2F%2Fbetslip-history%2Fdetail%3Fid%3DeyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUTQxMUVTVlNEUjAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.USyWtik_M1Vz2wMwmJlGLgCmE7GnQY3lKJes04SqocE%26source%3DSB"
    "https://applink.psk.hr/ticketdetail?id=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUTZGODdOOTlFUjAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0._qqxST7pPvQ0UvnMacElkmEZna-Msv-VqBsocLq93OI&source=SB&deeplink=ftnhr%3A%2F%2Fbetslip-history%2Fdetail%3Fid%3DeyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUTZGODdOOTlFUjAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0._qqxST7pPvQ0UvnMacElkmEZna-Msv-VqBsocLq93OI%26source%3DSB"
    "https://applink.psk.hr/ticketdetail?id=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUThFSkYyWjFFMDAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.oB_G41oVqzxsAkPwya5oEH2v7Bl4HZSlME0c1Fnjals&source=SB&deeplink=ftnhr%3A%2F%2Fbetslip-history%2Fdetail%3Fid%3DeyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUThFSkYyWjFFMDAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.oB_G41oVqzxsAkPwya5oEH2v7Bl4HZSlME0c1Fnjals%26source%3DSB"
    "https://applink.psk.hr/ticketdetail?id=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUUFISEs1WlNFUjAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.aiQ5QZaqs8lq0HzA6sUSdsIc7eOfffFZevCUE-qp-Mw&source=SB&deeplink=ftnhr%3A%2F%2Fbetslip-history%2Fdetail%3Fid%3DeyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUUFISEs1WlNFUjAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.aiQ5QZaqs8lq0HzA6sUSdsIc7eOfffFZevCUE-qp-Mw%26source%3DSB"
    "https://applink.psk.hr/ticketdetail?id=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUUQwSkNTWEhFMDAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.C0g9WBioNn-bXpDU3KnrGBaAsFa6UmCN9itgM7EgLHY&source=SB&deeplink=ftnhr%3A%2F%2Fbetslip-history%2Fdetail%3Fid%3DeyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUUQwSkNTWEhFMDAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.C0g9WBioNn-bXpDU3KnrGBaAsFa6UmCN9itgM7EgLHY%26source%3DSB"
    "https://applink.psk.hr/ticketdetail?id=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUUVTQjI3MDFFRzAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.NEq_yC8n023mIioEnMHW5rJZ8lBvspb3udTKGBOrowM&source=SB&deeplink=ftnhr%3A%2F%2Fbetslip-history%2Fdetail%3Fid%3DeyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUUVTQjI3MDFFRzAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.NEq_yC8n023mIioEnMHW5rJZ8lBvspb3udTKGBOrowM%26source%3DSB"
    "https://applink.psk.hr/ticketdetail?id=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUUhDVFNXMzFFMDAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.kJPWSue0Gecx0pqL8gc0AcFesKv_lvCZuLsNHAqkhbM&source=SB&deeplink=ftnhr%3A%2F%2Fbetslip-history%2Fdetail%3Fid%3DeyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUUhDVFNXMzFFMDAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.kJPWSue0Gecx0pqL8gc0AcFesKv_lvCZuLsNHAqkhbM%26source%3DSB"
    "https://applink.psk.hr/ticketdetail?id=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUUtYWlZCNVNGRzAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.QF0y1y8sGoTQOVmZrFszqxK3WsKAi233-ldLogAlfPU&source=SB&deeplink=ftnhr%3A%2F%2Fbetslip-history%2Fdetail%3Fid%3DeyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUUtYWlZCNVNGRzAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.QF0y1y8sGoTQOVmZrFszqxK3WsKAi233-ldLogAlfPU%26source%3DSB"
    "https://applink.psk.hr/ticketdetail?id=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUVBHRVBTTTFIMDAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.ovjBJduXaXpnVAxFddonJGpiHeVUoXQVd2n9dHkqYrg&source=SB&deeplink=ftnhr%3A%2F%2Fbetslip-history%2Fdetail%3Fid%3DeyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUVBHRVBTTTFIMDAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.ovjBJduXaXpnVAxFddonJGpiHeVUoXQVd2n9dHkqYrg%26source%3DSB"
    "https://applink.psk.hr/ticketdetail?id=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUVJIMzRLRVNIRzAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.tAxIvLAACIIKelaPcoSGjOaERA7lAUYbz6GAh_ft_rU&source=SB&deeplink=ftnhr%3A%2F%2Fbetslip-history%2Fdetail%3Fid%3DeyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUVJIMzRLRVNIRzAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.tAxIvLAACIIKelaPcoSGjOaERA7lAUYbz6GAh_ft_rU%26source%3DSB"
    "https://applink.psk.hr/ticketdetail?id=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUVRFMTJNMDFIRzAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.bEFiFuE4KrQuBXclqInWyA5MJbbyOFoKSE16VXxPa08&source=SB&deeplink=ftnhr%3A%2F%2Fbetslip-history%2Fdetail%3Fid%3DeyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUVRFMTJNMDFIRzAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.bEFiFuE4KrQuBXclqInWyA5MJbbyOFoKSE16VXxPa08%26source%3DSB"
    "https://applink.psk.hr/ticketdetail?id=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUVgwOVpENFNIRzAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.xWz-Hu8WvbJCNUP6Vk6t90ZA0gLY89H624rr72QxUVk&source=SB&deeplink=ftnhr%3A%2F%2Fbetslip-history%2Fdetail%3Fid%3DeyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUVgwOVpENFNIRzAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.xWz-Hu8WvbJCNUP6Vk6t90ZA0gLY89H624rr72QxUVk%26source%3DSB"
    "https://applink.psk.hr/ticketdetail?id=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUVpIU0gyUkhIUjAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.-EoNz9eo1pKYei7W0qahrC0hmUELqQDjt7mTAbUZS6o&source=SB&deeplink=ftnhr%3A%2F%2Fbetslip-history%2Fdetail%3Fid%3DeyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUVpIU0gyUkhIUjAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.-EoNz9eo1pKYei7W0qahrC0hmUELqQDjt7mTAbUZS6o%26source%3DSB"
    "https://applink.psk.hr/ticketdetail?id=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUjFEOUs5QTFLRzAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.nNDEqhq8EVn8I8P2W46HGfvhnW09ZacxZsVB4Jy1xpo&source=SB&deeplink=ftnhr%3A%2F%2Fbetslip-history%2Fdetail%3Fid%3DeyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJIUFAwUjFEOUs5QTFLRzAwIiwicHJmIjoiUFVCTElDIiwic3JjIjoiU0IiLCJpc3MiOiJmb3J0dW5hd2ViIn0.nNDEqhq8EVn8I8P2W46HGfvhnW09ZacxZsVB4Jy1xpo%26source%3DSB"
)

# ── Colours ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

cleanup() { rm -f "$COOKIE_JAR"; }
trap cleanup EXIT

# ── Login ─────────────────────────────────────────────────────────────────────
echo -e "${YELLOW}Logging in as '${USERNAME}'...${NC}"

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -c "$COOKIE_JAR" \
    -X POST "${BASE_URL}/login" \
    -d "username=${USERNAME}&password=${PASSWORD}" \
    --max-redirs 5)



# Verify we actually got a session cookie
if ! grep -q "session" "$COOKIE_JAR" 2>/dev/null; then
    echo -e "${RED}Login failed — no session cookie received.${NC}"
    exit 1
fi

echo -e "${GREEN}Login successful.${NC}\n"

# ── Submit tickets ────────────────────────────────────────────────────────────
TOTAL=${#TICKETS[@]}
SUCCESS=0
FAIL=0

for i in "${!TICKETS[@]}"; do
    URL="${TICKETS[$i]}"
    NUM=$((i + 1))

    echo -e "${YELLOW}[${NUM}/${TOTAL}]${NC} Submitting: ${URL:0:80}..."

    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        -b "$COOKIE_JAR" \
        -c "$COOKIE_JAR" \
        -X POST "${BASE_URL}/" \
        -d "ticket_number=${URL}")

    if [[ "$HTTP_CODE" == "302" ]]; then
        echo -e "  ${GREEN}✓ Added (HTTP ${HTTP_CODE})${NC}"
        SUCCESS=$((SUCCESS + 1))
    else
        echo -e "  ${RED}✗ Failed (HTTP ${HTTP_CODE})${NC}"
        FAIL=$((FAIL + 1))
    fi

done

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "────────────────────────────────────"
echo -e "Done. ${GREEN}${SUCCESS} added${NC} / ${RED}${FAIL} failed${NC} out of ${TOTAL} tickets."
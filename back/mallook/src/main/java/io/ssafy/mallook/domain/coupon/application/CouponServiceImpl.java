package io.ssafy.mallook.domain.coupon.application;

import io.ssafy.mallook.domain.coupon.dao.CouponRepository;
import io.ssafy.mallook.domain.coupon.dto.response.CouponRes;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class CouponServiceImpl implements CouponService{
    private final CouponRepository couponRepository;
    @Override
    @Transactional(readOnly = true)
    public List<CouponRes> findMyCouponList(Pageable pageable, UUID memberId) {
        return couponRepository.findAllByMemberId(pageable, memberId);
    }

}